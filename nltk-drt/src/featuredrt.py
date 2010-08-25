from nltk import load_parser
from nltk.sem.logic import ParseException
from nltk.sem.logic import Variable
from temporaldrt import unique_variable, DrtImpExpression, DrtAbstractVariableExpression, DrtIndividualVariableExpression, DrtLambdaExpression, DrtEventVariableExpression, DrtConstantExpression, DRS, DrtTokens, DrtParser, DrtApplicationExpression, DrtVariableExpression, ConcatenationDRS, PossibleAntecedents, AnaphoraResolutionException

class FeatureDrtTokens(DrtTokens):
    REFLEXIVE_PRONOUN = 'REFPRO'
    POSSESSIVE_PRONOUN = 'POSPRO'
    OPEN_BRACE = '{'
    CLOSE_BRACE = '}'
    PUNCT = [OPEN_BRACE, CLOSE_BRACE]
    SYMBOLS = DrtTokens.SYMBOLS + PUNCT
    TOKENS = DrtTokens.TOKENS + PUNCT

def get_refs(self, recursive=False):
    return []

from nltk.sem.drt import AbstractDrs

AbstractDrs.get_refs = get_refs

class FeatureExpression(DrtConstantExpression):
    """An expression with syntactic features attached"""
    def __init__(self, expression, features):
        self.variable = expression
        self.features = features

    def substitute_bindings(self, bindings):
        #print "FeatureConstantExpression.substitute_bindings(%s)" % (bindings)
        expression = self.variable.substitute_bindings(bindings)

        features = []
        for var in self.features:
            try:
                val = bindings[var]
                if not isinstance(val, str):
                    raise ValueError('expected a string feature value')
                features.append(val)
            except KeyError:
                pass

        return self._make_DrtLambdaExpression(expression, features)

    def _make_DrtLambdaExpression(self, expression, features):
        if isinstance(expression, DrtLambdaExpression) and\
        isinstance(expression.term, ConcatenationDRS) and\
        isinstance(expression.term.first, DRS) and\
        expression.term.second.argument.variable in expression.term.first.refs:
            features_map = {expression.term.second.argument.variable: features}
            if isinstance(expression.term.first, FeatureDRS):
                features_map.update(expression.term.first.features)
            return DrtLambdaExpression(expression.variable, ConcatenationFeatureDRS(FeatureDRS(expression.term.first.refs, expression.term.first.conds, features_map), expression.term.second))
        elif isinstance(expression, DrtLambdaExpression) and\
        isinstance(expression.term, DRS) and\
        len(expression.term.conds) == 1 and\
        isinstance(expression.term.conds[0], DrtImpExpression) and\
        isinstance(expression.term.conds[0].first, DRS) and\
        expression.term.conds[0].second.argument.variable in expression.term.conds[0].first.refs:
            #print type(expression.term.conds[0])
            features_map = {expression.term.conds[0].second.argument.variable: features}
            return DrtLambdaExpression(expression.variable, FeatureDRS(expression.term.refs, [DrtImpExpression(FeatureDRS(expression.term.conds[0].first.refs, expression.term.conds[0].first.conds, features_map), expression.term.conds[0].second)]))

        else:
            print "expression:", expression, type(expression), type(expression.term), type(expression.term.first)
            raise NotImplementedError()

class FeatureDRS(DRS):
    """Discourse Representation Structure where referents can have features."""
    def __init__(self, refs, conds, features={}):
        """
        @param refs: C{list} of C{DrtIndividualVariableExpression} for the 
        discourse referents
        @param conds: C{list} of C{Expression} for the conditions
        """ 
        self.refs = refs
        self.conds = conds
        self.features = features

    def __add__(self, other):
        return ConcatenationFeatureDRS(self, other)
    
    def _replace_features(self, var, new_var):
        try:
            data = self.features[var]
            features = dict(self.features)
            del features[var]
            features[new_var] = data
        except KeyError:
            features = self.features
        return features

    def replace(self, variable, expression, replace_bound=False):

        """Replace all instances of variable v with expression E in self,
        where v is free in self."""

        try:
            #if a bound variable is the thing being replaced
            i = self.refs.index(variable)
            if not replace_bound:
                return self
            else:
                return FeatureDRS(self.refs[:i] + [expression.variable] + self.refs[i + 1:],
                           [cond.replace(variable, expression, True) for cond in self.conds],
                           self._replace_features(variable, expression.variable))
        except ValueError:
            #variable not bound by this DRS
            
            # any bound variable that appears in the expression must
            # be alpha converted to avoid a conflict
            for ref in (set(self.refs) & expression.free()):
                newvar = unique_variable(ref) 
                newvarex = DrtVariableExpression(newvar)
                i = self.refs.index(ref)
                self = FeatureDRS(self.refs[:i] + [newvar] + self.refs[i + 1:],
                           [cond.replace(ref, newvarex, True) for cond in self.conds],
                            self._replace_features(ref, newvar))

            #replace in the conditions
            return FeatureDRS(self.refs,
                       [cond.replace(variable, expression, replace_bound) 
                        for cond in self.conds],
                        self.features)

    def simplify(self):
        return FeatureDRS(self.refs, [cond.simplify() for cond in self.conds], self.features)
    
    def resolve(self, trail=[]):
        r_conds = []
        for cond in self.conds:
            r_cond = cond.resolve(trail + [self])            
            r_conds.append(r_cond)
        return self.__class__(self.refs, r_conds, self.features)

    def str(self, syntax=DrtTokens.NLTK):
        if syntax == DrtTokens.PROVER9:
            return self.fol().str(syntax)
        else:
            refs = []
            for ref in self.refs:
                features = ""
                if ref in self.features:
                    features = '{' + ','.join(self.features[ref]) +'}'
                refs.append(str(ref) + features)
            return '([%s],[%s])' % (','.join(refs),
                                    ', '.join([c.str(syntax) for c in self.conds]))

    def _compare_features(self, other):
        if len(self.features) != len(other.features):
            return False
        for var, features in self.features.iteritems():
            if features != other.features[var]:
                return False

        return True

    def __eq__(self, other):
        r"""Defines equality modulo alphabetic variance.
        If we are comparing \x.M  and \y.N, then check equality of M and N[x/y]."""
        if isinstance(other, DRS):
            if len(self.refs) == len(other.refs):
                converted_other = other
                for (r1, r2) in zip(self.refs, converted_other.refs):
                    varex = self.make_VariableExpression(r1)
                    converted_other = converted_other.replace(r2, varex, True)
                return self.conds == converted_other.conds and self._compare_features(converted_other)
        return False

class ConcatenationFeatureDRS(ConcatenationDRS):
    def simplify(self):
        #print "ConcatenationEventDRS.simplify(%s)" % (self)
        first = self.first.simplify()
        second = self.second.simplify()
        
        def _alpha_covert_second(first, second):
            # For any ref that is in both 'first' and 'second'
            for ref in (set(first.get_refs(True)) & set(second.get_refs(True))):
                # alpha convert the ref in 'second' to prevent collision
                newvar = DrtVariableExpression(unique_variable(ref))
                second = second.replace(ref, newvar, True)
            return second

        if isinstance(first, FeatureDRS) and isinstance(second, FeatureDRS):
            second = _alpha_covert_second(first, second)
            features = dict(first.features)
            for idx,ref in enumerate(first.refs):
                if ref not in first.features and idx in second.features:
                    features[ref] = second.features[idx]

            features.update(second.features)
            return FeatureDRS(first.refs + second.refs, first.conds + second.conds, features)

        elif isinstance(first, FeatureDRS) and isinstance(second, DRS):
            second = _alpha_covert_second(first, second)
            return FeatureDRS(first.refs + second.refs, first.conds + second.conds, first.features)

        elif isinstance(first, DRS) and isinstance(second, FeatureDRS):
            second = _alpha_covert_second(first, second)
            return FeatureDRS(first.refs + second.refs, first.conds + second.conds, second.features)

        else:
            return ConcatenationDRS.simplify(self)

class FeatureDrtParser(DrtParser):
    """A lambda calculus expression parser."""

    def get_all_symbols(self):
        return FeatureDrtTokens.SYMBOLS

    def isvariable(self, tok):
        return tok not in FeatureDrtTokens.TOKENS

    def handle_variable(self, tok, context):
        var = DrtParser.handle_variable(self, tok, context)
        if isinstance(var, DrtConstantExpression): #or isinstance(var, DrtApplicationExpression):
            # handle the feature structure of the variable
            try:
                if self.token(0) == FeatureDrtTokens.OPEN_BRACE:
                    self.token() # swallow the OPEN_BRACE
                    features = []
                    while self.token(0) != FeatureDrtTokens.CLOSE_BRACE:
                        features.append(Variable(self.token()))
                        
                        if self.token(0) == DrtTokens.COMMA:
                            self.token() # swallow the comma
                    self.token() # swallow the CLOSE_BRACE
                    return FeatureExpression(var, features)
            except ParseException:
                #we reached the end of input, this constant has no features
                pass
        return var

    def handle_DRS(self, tok, context):
        # a DRS
        self.assertNextToken(DrtTokens.OPEN_BRACKET)
        refs = []
        features = {}
        while self.inRange(0) and self.token(0) != DrtTokens.CLOSE_BRACKET:
            # Support expressions like: DRS([x y],C) == DRS([x,y],C)
            if refs and self.token(0) == DrtTokens.COMMA:
                self.token() # swallow the comma
            ref = self.get_next_token_variable('quantified')
            if self.token(0) == FeatureDrtTokens.OPEN_BRACE:
                self.token() # swallow the OPEN_BRACE
                ref_features = []
                while self.token(0) != FeatureDrtTokens.CLOSE_BRACE:
                    ref_features.append(self.token())
                    
                    if self.token(0) == DrtTokens.COMMA:
                        self.token() # swallow the comma
                self.token() # swallow the CLOSE_BRACE
                features[ref] = ref_features
            refs.append(ref)
        self.assertNextToken(DrtTokens.CLOSE_BRACKET)
        
        if self.inRange(0) and self.token(0) == DrtTokens.COMMA: #if there is a comma (it's optional)
            self.token() # swallow the comma
            
        self.assertNextToken(DrtTokens.OPEN_BRACKET)
        conds = []
        while self.inRange(0) and self.token(0) != DrtTokens.CLOSE_BRACKET:
            # Support expressions like: DRS([x y],C) == DRS([x, y],C)
            if conds and self.token(0) == DrtTokens.COMMA:
                self.token() # swallow the comma
            conds.append(self.parse_Expression(context))
        self.assertNextToken(DrtTokens.CLOSE_BRACKET)
        self.assertNextToken(DrtTokens.CLOSE)
        
        if features:
            return FeatureDRS(refs, conds, features)
        else:
            return DRS(refs, conds)

    def make_ApplicationExpression(self, function, argument):
        """ Is self of the form "PRO(x)"? """
        if isinstance(function, DrtAbstractVariableExpression) and \
               function.variable.name == FeatureDrtTokens.PRONOUN and \
               isinstance(argument, DrtIndividualVariableExpression):
            return DrtPronounApplicationExpression(function, argument)

        """ Is self of the form "REFPRO(x)"? """
        if isinstance(function, DrtAbstractVariableExpression) and \
               function.variable.name == FeatureDrtTokens.REFLEXIVE_PRONOUN and \
               isinstance(argument, DrtIndividualVariableExpression):
            return DrtReflexivePronounApplicationExpression(function, argument)

        """ Is self of the form "POSPRO(x)"? """
        if isinstance(function, DrtAbstractVariableExpression) and \
               function.variable.name == FeatureDrtTokens.POSSESSIVE_PRONOUN and \
               isinstance(argument, DrtIndividualVariableExpression):
            return DrtPossessivePronounApplicationExpression(function, argument)

        elif isinstance(argument, DrtEventVariableExpression):
            return DrtEventApplicationExpression(function, argument)

        elif isinstance(function, DrtEventApplicationExpression):
            return DrtRoleApplicationExpression(function, argument)

        else:
            return DrtParser.make_ApplicationExpression(self, function, argument)

    def get_BooleanExpression_factory(self, tok):
        """This method serves as a hook for other logic parsers that
        have different boolean operators"""
        if tok == DrtTokens.DRS_CONC:
            return ConcatenationFeatureDRS
        else:
            return DrtParser.get_BooleanExpression_factory(self, tok)

class DrtEventApplicationExpression(DrtApplicationExpression):
    pass

class DrtRoleApplicationExpression(DrtApplicationExpression):
    def get_role(self):
        return self.function.function
    def get_variable(self):
        return self.argument.variable
    def get_event(self):
        return self.function.argument

class DrtPronounApplicationExpression(DrtApplicationExpression):
    def resolve(self, trail=[]):
        possible_antecedents = PossibleEventAntecedents()
        pronouns = []
        pro_var = self.argument.variable
        roles = {}
        events = {}
        pro_role = None
        pro_event = None
        pro_features = None
        features = {}
        refs = []
        for ancestor in trail:
            if isinstance(ancestor, FeatureDRS):
                features.update(ancestor.features)
                refs.extend(ancestor.refs)
                if pro_var in features:
                    #print features
                    if not pro_features:
                        pro_features = features[pro_var]
                    for cond in ancestor.conds:
                        #look for role assigning expressions:
                        if isinstance(cond, DrtRoleApplicationExpression):
                            var = cond.get_variable()
                            #filter out the variable itself
                            #filter out the variables with non-matching features
                            #allow only backward resolution
                            if not var == pro_var:
                                if features[var] == pro_features and refs.index(var) <  refs.index(pro_var):
                                    possible_antecedents.append((self.make_VariableExpression(var), 0))
                                    roles[var] = cond.get_role()
                                    events[var] = cond.get_event()
                            else:
                                pro_role = cond.get_role()
                                pro_event = cond.get_event()
    
                        elif cond.is_pronoun_function():
                            pronouns.append(cond.argument)

        #exclude pronouns from resolution
        #possible_antecedents = possible_antecedents.exclude(pronouns)

        #non reflexive pronouns can not resolve to variables having a role in the same event
        antecedents = PossibleEventAntecedents()
        
        is_reflexive = isinstance(self, DrtReflexivePronounApplicationExpression)
        is_possessive = isinstance(self, DrtPossessivePronounApplicationExpression)
        if not is_reflexive:
            possible_antecedents = possible_antecedents.exclude(pronouns)
        for index, (var, rank) in enumerate(possible_antecedents):
            if not is_reflexive and not events[var.variable] == pro_event:
                antecedents.append((var, rank))
            elif (is_reflexive or is_possessive) and events[var.variable] == pro_event:
                antecedents.append((var, rank))

        #ranking system
        #increment ranking for matching roles and map the positions of antecedents
        if len(antecedents) > 1:
            idx_map = {}
            for index, (var, rank) in enumerate(antecedents):
                idx_map[refs.index(var.variable)] = var
                if roles[var.variable] == pro_role:
                    antecedents[index] = (var, rank+1)

            #rank by proximity

            for i,key in enumerate(sorted(idx_map)):
                j = antecedents.index(idx_map[key])
                antecedents[j] = (antecedents[j][0], antecedents[j][1]+i)

        if len(antecedents) == 0:
            raise AnaphoraResolutionException("Variable '%s' does not "
                                "resolve to anything." % self.argument)
        elif len(antecedents) == 1:
            resolution = antecedents[0][0]
        else:
            resolution = antecedents

        return self.make_EqualityExpression(self.argument, resolution)

class DrtReflexivePronounApplicationExpression(DrtPronounApplicationExpression):
    pass

class DrtPossessivePronounApplicationExpression(DrtPronounApplicationExpression):
    pass

class PossibleEventAntecedents(PossibleAntecedents):

    def free(self, indvar_only=True):
        """Set of free variables."""
        return set([item[0] for item in self])

    def replace(self, variable, expression, replace_bound=False):
        """Replace all instances of variable v with expression E in self,
        where v is free in self."""
        result = PossibleEventAntecedents()
        for item in self:
            if item[0] == variable:
                result.append(expression, item[1])
            else:
                result.append(item)
        return result
            
    def exclude(self, vars):
        result = PossibleEventAntecedents()
        for item in self:
            if item[0] not in vars:
                result.append(item)
        return result
        
    def index(self, variable):
        for i, item in enumerate(self):
            if item[0] == variable:
                return i
        raise ValueError, type(variable)
            
    def str(self, syntax=DrtTokens.NLTK):
        return '[' +  ','.join([str(item[0]) + "(" + str(item[1]) + ")" for item in self]) + ']'