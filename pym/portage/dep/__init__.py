# deps.py -- Portage dependency resolution functions
# Copyright 2003-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = [
	'Atom', 'best_match_to_list', 'cpvequal',
	'dep_getcpv', 'dep_getkey', 'dep_getslot',
	'dep_getusedeps', 'dep_opconvert', 'flatten',
	'get_operator', 'isjustname', 'isspecific',
	'isvalidatom', 'match_from_list', 'match_to_list',
	'paren_enclose', 'paren_normalize', 'paren_reduce',
	'remove_slot', 'strip_empty', 'use_reduce', 
	'_repo_separator', '_slot_separator',
]

# DEPEND SYNTAX:
#
# 'use?' only affects the immediately following word!
# Nesting is the only legal way to form multiple '[!]use?' requirements.
#
# Where: 'a' and 'b' are use flags, and 'z' is a depend atom.
#
# "a? z"           -- If 'a' in [use], then b is valid.
# "a? ( z )"       -- Syntax with parenthesis.
# "a? b? z"        -- Deprecated.
# "a? ( b? z )"    -- Valid
# "a? ( b? ( z ) ) -- Valid
#

import re, sys
import warnings
from itertools import chain
import portage.exception
from portage.eapi import eapi_has_slot_deps, eapi_has_src_uri_arrows, \
	eapi_has_use_deps, eapi_has_strong_blocks, eapi_has_use_dep_defaults
from portage.exception import InvalidAtom, InvalidData, InvalidDependString
from portage.localization import _
from portage.versions import catpkgsplit, catsplit, \
	pkgcmp, ververify, _cp, _cpv
import portage.cache.mappings

if sys.hexversion >= 0x3000000:
	basestring = str

# Api consumers included in portage should set this to True.
# Once the relevant api changes are in a portage release with
# stable keywords, make these warnings unconditional.
_internal_warnings = False

def cpvequal(cpv1, cpv2):
	"""
	
	@param cpv1: CategoryPackageVersion (no operators) Example: "sys-apps/portage-2.1"
	@type cpv1: String
	@param cpv2: CategoryPackageVersion (no operators) Example: "sys-apps/portage-2.1"
	@type cpv2: String
	@rtype: Boolean
	@returns:
	1.  True if cpv1 = cpv2
	2.  False Otherwise
	3.  Throws PortageException if cpv1 or cpv2 is not a CPV

	Example Usage:
	>>> from portage.dep import cpvequal
	>>> cpvequal("sys-apps/portage-2.1","sys-apps/portage-2.1")
	>>> True

	"""

	split1 = catpkgsplit(cpv1)
	split2 = catpkgsplit(cpv2)
	
	if not split1 or not split2:
		raise portage.exception.PortageException(_("Invalid data '%s, %s', parameter was not a CPV") % (cpv1, cpv2))
	
	if split1[0] != split2[0]:
		return False
	
	return (pkgcmp(split1[1:], split2[1:]) == 0)

def strip_empty(myarr):
	"""
	Strip all empty elements from an array

	@param myarr: The list of elements
	@type myarr: List
	@rtype: Array
	@return: The array with empty elements removed
	"""
	warnings.warn(_("%s is deprecated and will be removed without replacement.") % \
		('portage.dep.strip_empty',), DeprecationWarning, stacklevel=2)
	return [x for x in myarr if x]

def paren_reduce(mystr):
	"""
	Take a string and convert all paren enclosed entities into sublists and
	split the list elements by spaces. All redundant brackets are removed.

	Example usage:
		>>> paren_reduce('foobar foo? ( bar baz )')
		['foobar', 'foo?', ['bar', 'baz']]

	@param mystr: The string to reduce
	@type mystr: String
	@rtype: Array
	@return: The reduced string in an array
	"""
	if _internal_warnings:
		warnings.warn(_("%s is deprecated and will be removed without replacement.") % \
			('portage.dep.paren_reduce',), DeprecationWarning, stacklevel=2)
	mysplit = mystr.split()
	level = 0
	stack = [[]]
	need_bracket = False

	for token in mysplit:
		if token == "(":
			need_bracket = False
			stack.append([])
			level += 1
		elif token == ")":
			if need_bracket:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
			if level > 0:
				level -= 1
				l = stack.pop()
				is_single = (len(l) == 1 or (len(l)==2 and (l[0] == "||" or l[0][-1] == "?")))

				def ends_in_any_of_dep(k):
					return k>=0 and stack[k] and stack[k][-1] == "||"

				def ends_in_operator(k):
					return k>=0 and stack[k] and (stack[k][-1] == "||" or stack[k][-1][-1] == "?")

				def special_append():
					"""
					Use extend instead of append if possible. This kills all redundant brackets.
					"""
					if is_single and (not stack[level] or not stack[level][-1][-1] == "?"):
						if len(l) == 1 and isinstance(l[0], list):
							# l = [[...]]
							stack[level].extend(l[0])
						else:
							stack[level].extend(l)
					else:	
						stack[level].append(l)

				if l:
					if not ends_in_any_of_dep(level-1) and not ends_in_operator(level):
						#Optimize: ( ( ... ) ) -> ( ... ). Make sure there is no '||' hanging around.
						stack[level].extend(l)
					elif not stack[level]:
						#An '||' in the level above forces us to keep to brackets.
						special_append()
					elif len(l) == 1 and ends_in_any_of_dep(level):
						#Optimize: || ( A ) -> A
						stack[level].pop()
						special_append()
					elif len(l) == 2 and (l[0] == "||" or l[0][-1] == "?") and stack[level][-1] in (l[0], "||"):
						#Optimize: 	|| ( || ( ... ) ) -> || ( ... )
						#			foo? ( foo? ( ... ) ) -> foo? ( ... )
						#			|| ( foo? ( ... ) ) -> foo? ( ... )
						stack[level].pop()
						special_append()
					else:
						special_append()
				else:
					if stack[level] and (stack[level][-1] == "||" or stack[level][-1][-1] == "?"):
						stack[level].pop()
			else:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
		elif token == "||":
			if need_bracket:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
			need_bracket = True
			stack[level].append(token)
		else:
			if need_bracket:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % mystr)

			if token[-1] == "?":
				need_bracket = True
			
			stack[level].append(token)

	if level != 0 or need_bracket:
		raise InvalidDependString(
			_("malformed syntax: '%s'") % mystr)
	
	return stack[0]

class paren_normalize(list):
	"""Take a dependency structure as returned by paren_reduce or use_reduce
	and generate an equivalent structure that has no redundant lists."""
	def __init__(self, src):
		if _internal_warnings:
			warnings.warn(_("%s is deprecated and will be removed without replacement.") % \
				('portage.dep.paren_normalize',), DeprecationWarning, stacklevel=2)
		list.__init__(self)
		self._zap_parens(src, self)

	def _zap_parens(self, src, dest, disjunction=False):
		if not src:
			return dest
		i = iter(src)
		for x in i:
			if isinstance(x, basestring):
				if x in ('||', '^^'):
					y = self._zap_parens(next(i), [], disjunction=True)
					if len(y) == 1:
						dest.append(y[0])
					else:
						dest.append(x)
						dest.append(y)
				elif x.endswith("?"):
					dest.append(x)
					dest.append(self._zap_parens(next(i), []))
				else:
					dest.append(x)
			else:
				if disjunction:
					x = self._zap_parens(x, [])
					if len(x) == 1:
						dest.append(x[0])
					else:
						dest.append(x)
				else:
					self._zap_parens(x, dest)
		return dest

def paren_enclose(mylist, unevaluated_atom=False):
	"""
	Convert a list to a string with sublists enclosed with parens.

	Example usage:
		>>> test = ['foobar','foo',['bar','baz']]
		>>> paren_enclose(test)
		'foobar foo ( bar baz )'

	@param mylist: The list
	@type mylist: List
	@rtype: String
	@return: The paren enclosed string
	"""
	mystrparts = []
	for x in mylist:
		if isinstance(x, list):
			mystrparts.append("( "+paren_enclose(x)+" )")
		else:
			if unevaluated_atom:
				x = getattr(x, 'unevaluated_atom', x)
			mystrparts.append(x)
	return " ".join(mystrparts)

def use_reduce(depstr, uselist=[], masklist=[], matchall=False, excludeall=[], is_src_uri=False, \
	eapi=None, opconvert=False, flat=False, is_valid_flag=None, token_class=None, matchnone=False):
	"""
	Takes a dep string and reduces the use? conditionals out, leaving an array
	with subarrays. All redundant brackets are removed.

	@param deparray: depstring
	@type deparray: String
	@param uselist: List of use enabled flags
	@type uselist: List
	@param masklist: List of masked flags (always treated as disabled)
	@type masklist: List
	@param matchall: Treat all conditionals as active. Used by repoman. 
	@type matchall: Bool
	@param excludeall: List of flags for which negated conditionals are always treated as inactive.
	@type excludeall: List
	@param is_src_uri: Indicates if depstr represents a SRC_URI
	@type is_src_uri: Bool
	@param eapi: Indicates the EAPI the dep string has to comply to
	@type eapi: String
	@param opconvert: Put every operator as first element into it's argument list
	@type opconvert: Bool
	@param flat: Create a flat list of all tokens
	@type flat: Bool
	@param is_valid_flag: Function that decides if a given use flag might be used in use conditionals
	@type is_valid_flag: Function
	@param token_class: Convert all non operator tokens into this class
	@type token_class: Class
	@param matchnone: Treat all conditionals as inactive. Used by digestgen(). 
	@type matchnone: Bool
	@rtype: List
	@return: The use reduced depend array
	"""
	if isinstance(depstr, list):
		if _internal_warnings:
			warnings.warn(_("Passing paren_reduced dep arrays to %s is deprecated. " + \
				"Pass the original dep string instead.") % \
				('portage.dep.use_reduce',), DeprecationWarning, stacklevel=2)
		depstr = paren_enclose(depstr)

	if opconvert and flat:
		raise ValueError("portage.dep.use_reduce: 'opconvert' and 'flat' are mutually exclusive")

	if matchall and matchnone:
		raise ValueError("portage.dep.use_reduce: 'matchall' and 'matchnone' are mutually exclusive")

	useflag_re = _get_useflag_re(eapi)

	def is_active(conditional):
		"""
		Decides if a given use conditional is active.
		"""
		if conditional.startswith("!"):
			flag = conditional[1:-1]
			is_negated = True
		else:
			flag = conditional[:-1]
			is_negated = False
		
		if is_valid_flag:
			if not is_valid_flag(flag):
				msg = _("USE flag '%s' referenced in " + \
					"conditional '%s' is not in IUSE") \
					% (flag, conditional)
				e = InvalidData(msg, category='IUSE.missing')
				raise InvalidDependString(msg, errors=(e,))
		else:
			if useflag_re.match(flag) is None:
				raise InvalidDependString(
					_("invalid use flag '%s' in conditional '%s'") % (flag, conditional))

		if is_negated and flag in excludeall:
			return False

		if flag in masklist:
			return is_negated

		if matchall:
			return True

		if matchnone:
			return False

		return (flag in uselist and not is_negated) or \
			(flag not in uselist and is_negated)

	def missing_white_space_check(token, pos):
		"""
		Used to generate good error messages for invalid tokens.
		"""
		for x in (")", "(", "||"):
			if token.startswith(x) or token.endswith(x):
				raise InvalidDependString(
					_("missing whitespace around '%s' at '%s', token %s") % (x, token, pos+1))

	mysplit = depstr.split()
	#Count the bracket level.
	level = 0
	#We parse into a stack. Every time we hit a '(', a new empty list is appended to the stack.
	#When we hit a ')', the last list in the stack is merged with list one level up.
	stack = [[]]
	#Set need_bracket to True after use conditionals or ||. Other tokens need to ensure
	#that need_bracket is not True.
	need_bracket = False
	#Set need_simple_token to True after a SRC_URI arrow. Other tokens need to ensure
	#that need_simple_token is not True.
	need_simple_token = False

	for pos, token in enumerate(mysplit):
		if token == "(":
			if need_simple_token:
				raise InvalidDependString(
					_("expected: file name, got: '%s', token %s") % (token, pos+1))
			need_bracket = False
			stack.append([])
			level += 1
		elif token == ")":
			if need_bracket:
				raise InvalidDependString(
					_("expected: '(', got: '%s', token %s") % (token, pos+1))
			if need_simple_token:
				raise InvalidDependString(
					_("expected: file name, got: '%s', token %s") % (token, pos+1))
			if level > 0:
				level -= 1
				l = stack.pop()

				is_single = len(l) == 1 or \
					(opconvert and l and l[0] == "||") or \
					(not opconvert and len(l)==2 and l[0] == "||")
				ignore = False

				if flat:
					#In 'flat' mode, we simply merge all lists into a single large one.
					if stack[level] and stack[level][-1][-1] == "?":
						#The last token before the '(' that matches the current ')'
						#was a use conditional. The conditional is removed in any case.
						#Merge the current list if needed.
						if is_active(stack[level][-1]):
							stack[level].pop()
							stack[level].extend(l)
						else:
							stack[level].pop()
					else:
						stack[level].extend(l)
					continue

				if stack[level]:
					if stack[level][-1] == "||" and not l:
						#Optimize: || ( ) -> .
						stack[level].pop()
					elif stack[level][-1][-1] == "?":
						#The last token before the '(' that matches the current ')'
						#was a use conditional, remove it and decide if we
						#have to keep the current list.
						if not is_active(stack[level][-1]):
							ignore = True
						stack[level].pop()

				def ends_in_any_of_dep(k):
					return k>=0 and stack[k] and stack[k][-1] == "||"

				def starts_with_any_of_dep(k):
					#'ends_in_any_of_dep' for opconvert
					return k>=0 and stack[k] and stack[k][0] == "||"

				def last_any_of_operator_level(k):
					#Returns the level of the last || operator if it is in effect for
					#the current level. It is not in effect, if there is a level, that
					#ends in a non-operator. This is almost equivalent to stack[level][-1]=="||",
					#expect that it skips empty levels.
					while k>=0:
						if stack[k]:
							if stack[k][-1] == "||":
								return k
							elif stack[k][-1][-1] != "?":
								return -1
						k -= 1
					return -1

				def special_append():
					"""
					Use extend instead of append if possible. This kills all redundant brackets.
					"""
					if is_single:
						#Either [A], [[...]] or [|| [...]]
						if l[0] == "||" and ends_in_any_of_dep(level-1):
							if opconvert:
								stack[level].extend(l[1:])
							else:
								stack[level].extend(l[1])
						elif len(l) == 1 and isinstance(l[0], list):
							# l = [[...]]
							last = last_any_of_operator_level(level-1)
							if last == -1:
								if opconvert and isinstance(l[0], list) \
									and l[0] and l[0][0] == '||':
									stack[level].append(l[0])
								else:
									stack[level].extend(l[0])
							else:
								if opconvert and l[0] and l[0][0] == "||":
									stack[level].extend(l[0][1:])
								else:
									stack[level].append(l[0])
						else:
							stack[level].extend(l)
					else:
						if opconvert and stack[level] and stack[level][-1] == '||':
							stack[level][-1] = ['||'] + l
						else:
							stack[level].append(l)

				if l and not ignore:
					#The current list is not empty and we don't want to ignore it because
					#of an inactive use conditional.
					if not ends_in_any_of_dep(level-1) and not ends_in_any_of_dep(level):
						#Optimize: ( ( ... ) ) -> ( ... ). Make sure there is no '||' hanging around.
						stack[level].extend(l)
					elif not stack[level]:
						#An '||' in the level above forces us to keep to brackets.
						special_append()
					elif is_single and ends_in_any_of_dep(level):
						#Optimize: || ( A ) -> A,  || ( || ( ... ) ) -> || ( ... )
						stack[level].pop()
						special_append()
					elif ends_in_any_of_dep(level) and ends_in_any_of_dep(level-1):
						#Optimize: || ( A || ( B C ) ) -> || ( A B C )
						stack[level].pop()
						stack[level].extend(l)
					else:
						if opconvert and ends_in_any_of_dep(level):
							#In opconvert mode, we have to move the operator from the level
							#above into the current list.
							stack[level].pop()
							stack[level].append(["||"] + l)
						else:
							special_append()

			else:
				raise InvalidDependString(
					_("no matching '%s' for '%s', token %s") % ("(", ")", pos+1))
		elif token == "||":
			if is_src_uri:
				raise InvalidDependString(
					_("any-of dependencies are not allowed in SRC_URI: token %s") % (pos+1,))
			if need_bracket:
				raise InvalidDependString(
					_("expected: '(', got: '%s', token %s") % (token, pos+1))
			need_bracket = True
			stack[level].append(token)
		elif token == "->":
			if need_simple_token:
				raise InvalidDependString(
					_("expected: file name, got: '%s', token %s") % (token, pos+1))
			if not is_src_uri:
				raise InvalidDependString(
					_("SRC_URI arrow are only allowed in SRC_URI: token %s") % (pos+1,))
			if eapi is None or not eapi_has_src_uri_arrows(eapi):
				raise InvalidDependString(
					_("SRC_URI arrow not allowed in EAPI %s: token %s") % (eapi, pos+1))
			need_simple_token = True
			stack[level].append(token)	
		else:
			missing_white_space_check(token, pos)

			if need_bracket:
				raise InvalidDependString(
					_("expected: '(', got: '%s', token %s") % (token, pos+1))

			if need_simple_token and "/" in token:
				#The last token was a SRC_URI arrow, make sure we have a simple file name.
				raise InvalidDependString(
					_("expected: file name, got: '%s', token %s") % (token, pos+1))

			if token[-1] == "?":
				need_bracket = True
			else:
				need_simple_token = False
				if token_class and not is_src_uri:
					#Add a hack for SRC_URI here, to avoid conditional code at the consumer level
					try:
						token = token_class(token, eapi=eapi,
							is_valid_flag=is_valid_flag)
					except InvalidAtom as e:
						raise InvalidDependString(
							_("Invalid atom (%s), token %s") \
							% (e, pos+1), errors=(e,))
					except SystemExit:
						raise
					except Exception as e:
						raise InvalidDependString(
							_("Invalid token '%s', token %s") % (token, pos+1))

					if not matchall and \
						hasattr(token, 'evaluate_conditionals'):
						token = token.evaluate_conditionals(uselist)

			stack[level].append(token)

	if level != 0:
		raise InvalidDependString(
			_("Missing '%s' at end of string") % (")",))
	
	if need_bracket:
		raise InvalidDependString(
			_("Missing '%s' at end of string") % ("(",))
			
	if need_simple_token:
		raise InvalidDependString(
			_("Missing file name at end of string"))

	return stack[0]

def dep_opconvert(deplist):
	"""
	Iterate recursively through a list of deps, if the
	dep is a '||' or '&&' operator, combine it with the
	list of deps that follows..

	Example usage:
		>>> test = ["blah", "||", ["foo", "bar", "baz"]]
		>>> dep_opconvert(test)
		['blah', ['||', 'foo', 'bar', 'baz']]

	@param deplist: A list of deps to format
	@type mydep: List
	@rtype: List
	@return:
		The new list with the new ordering
	"""
	if _internal_warnings:
		warnings.warn(_("%s is deprecated. Use %s with the opconvert parameter set to True instead.") % \
			('portage.dep.dep_opconvert', 'portage.dep.use_reduce'), DeprecationWarning, stacklevel=2)

	retlist = []
	x = 0
	while x != len(deplist):
		if isinstance(deplist[x], list):
			retlist.append(dep_opconvert(deplist[x]))
		elif deplist[x] == "||":
			retlist.append([deplist[x]] + dep_opconvert(deplist[x+1]))
			x += 1
		else:
			retlist.append(deplist[x])
		x += 1
	return retlist

def flatten(mylist):
	"""
	Recursively traverse nested lists and return a single list containing
	all non-list elements that are found.

	Example usage:
		>>> flatten([1, [2, 3, [4]]])
		[1, 2, 3, 4]

	@param mylist: A list containing nested lists and non-list elements.
	@type mylist: List
	@rtype: List
	@return: A single list containing only non-list elements.
	"""
	if _internal_warnings:
		warnings.warn(_("%s is deprecated and will be removed without replacement.") % \
			('portage.dep.flatten',), DeprecationWarning, stacklevel=2)

	newlist = []
	for x in mylist:
		if isinstance(x, list):
			newlist.extend(flatten(x))
		else:
			newlist.append(x)
	return newlist


_usedep_re = {
	"0": re.compile("^(?P<prefix>[!-]?)(?P<flag>[A-Za-z0-9][A-Za-z0-9+_@-]*)(?P<default>(\(\+\)|\(\-\))?)(?P<suffix>[?=]?)$"),
#	"5": re.compile("^(?P<prefix>[!-]?)(?P<flag>[A-Za-z0-9][A-Za-z0-9+_@.-]*)(?P<default>(\(\+\)|\(\-\))?)(?P<suffix>[?=]?)$"),
}

def _get_usedep_re(eapi):
	"""
	@param eapi: The EAPI
	@type eapi: String or None
	@rtype: regular expression object
	@return: A regular expression object that matches valid USE flags for the
		given eapi. If eapi is None then the latest supported EAPI is assumed.
	"""
	return _usedep_re["0"]
#	if eapi in ("0", "1", "2", "3_pre1", "3_pre2", "3", "4_pre1", "4"):
#		return _usedep_re["0"]
#	else:
#		return _usedep_re["5"]

class _use_dep(object):

	__slots__ = ("__weakref__", "eapi", "conditional", "missing_enabled", "missing_disabled",
		"disabled", "enabled", "tokens", "required")

	class _conditionals_class(object):
		__slots__ = ("enabled", "disabled", "equal", "not_equal")

		def items(self):
			for k in self.__slots__:
				v = getattr(self, k, None)
				if v:
					yield (k, v)

		def values(self):
			for k in self.__slots__:
				v = getattr(self, k, None)
				if v:
					yield v

	# used in InvalidAtom messages
	_conditional_strings = {
		'enabled' :     '%s?',
		'disabled':    '!%s?',
		'equal':        '%s=',
		'not_equal':   '!%s=',
	}

	def __init__(self, use, eapi, enabled_flags=None, disabled_flags=None, missing_enabled=None, \
		missing_disabled=None, conditional=None, required=None):

		self.eapi = eapi

		if enabled_flags is not None:
			#A shortcut for the classe's own methods.
			self.tokens = use
			if not isinstance(self.tokens, tuple):
				self.tokens = tuple(self.tokens)

			self.required = frozenset(required)
			self.enabled = frozenset(enabled_flags)
			self.disabled = frozenset(disabled_flags)
			self.missing_enabled = frozenset(missing_enabled)
			self.missing_disabled = frozenset(missing_disabled)
			self.conditional = None

			if conditional:
				self.conditional = self._conditionals_class()
				for k in "enabled", "disabled", "equal", "not_equal":
					setattr(self.conditional, k, frozenset(conditional.get(k, [])))

			return

		enabled_flags = set()
		disabled_flags = set()
		missing_enabled = set()
		missing_disabled = set()
		no_default = set()

		conditional = {}
		usedep_re = _get_usedep_re(self.eapi)

		for x in use:
			m = usedep_re.match(x)
			if m is None:
				raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))

			operator = m.group("prefix") + m.group("suffix")
			flag = m.group("flag")
			default = m.group("default")

			if not operator:
				enabled_flags.add(flag)
			elif operator == "-":
				disabled_flags.add(flag)
			elif operator == "?":
				conditional.setdefault("enabled", set()).add(flag)
			elif operator == "=":
				conditional.setdefault("equal", set()).add(flag)
			elif operator == "!=":
				conditional.setdefault("not_equal", set()).add(flag)
			elif operator == "!?":
				conditional.setdefault("disabled", set()).add(flag)
			else:
				raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))

			if default:
				if default == "(+)":
					if flag in missing_disabled or flag in no_default:
						raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))
					missing_enabled.add(flag)
				else:
					if flag in missing_enabled or flag in no_default:
						raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))
					missing_disabled.add(flag)
			else:
				if flag in missing_enabled or flag in missing_disabled:
					raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))
				no_default.add(flag)

		self.tokens = use
		if not isinstance(self.tokens, tuple):
			self.tokens = tuple(self.tokens)

		self.required = frozenset(no_default)

		self.enabled = frozenset(enabled_flags)
		self.disabled = frozenset(disabled_flags)
		self.missing_enabled = frozenset(missing_enabled)
		self.missing_disabled = frozenset(missing_disabled)
		self.conditional = None

		if conditional:
			self.conditional = self._conditionals_class()
			for k in "enabled", "disabled", "equal", "not_equal":
				setattr(self.conditional, k, frozenset(conditional.get(k, [])))

	def __bool__(self):
		return bool(self.tokens)

	if sys.hexversion < 0x3000000:
		__nonzero__ = __bool__

	def __str__(self):
		if not self.tokens:
			return ""
		return "[%s]" % (",".join(self.tokens),)

	def __repr__(self):
		return "portage.dep._use_dep(%s)" % repr(self.tokens)

	def evaluate_conditionals(self, use):
		"""
		Create a new instance with conditionals evaluated.

		Conditional evaluation behavior:

			parent state   conditional   result

			 x              x?            x
			-x              x?
			 x             !x?
			-x             !x?           -x

			 x              x=            x
			-x              x=           -x
			 x             !x=           -x
			-x             !x=            x

		Conditional syntax examples:

			Compact Form        Equivalent Expanded Form

			foo[bar?]           bar? ( foo[bar]  ) !bar? ( foo       )
			foo[!bar?]          bar? ( foo       ) !bar? ( foo[-bar] )
			foo[bar=]           bar? ( foo[bar]  ) !bar? ( foo[-bar] )
			foo[!bar=]          bar? ( foo[-bar] ) !bar? ( foo[bar]  )

		"""
		enabled_flags = set(self.enabled)
		disabled_flags = set(self.disabled)

		tokens = []
		usedep_re = _get_usedep_re(self.eapi)

		for x in self.tokens:
			m = usedep_re.match(x)

			operator = m.group("prefix") + m.group("suffix")
			flag = m.group("flag")
			default = m.group("default")
			if default is None:
				default = ""

			if operator == "?":
				if flag in use:
					enabled_flags.add(flag)
					tokens.append(flag+default)
			elif operator == "=":
				if flag in use:
					enabled_flags.add(flag)
					tokens.append(flag+default)
				else:
					disabled_flags.add(flag)
					tokens.append("-"+flag+default)
			elif operator == "!=":
				if flag in use:
					disabled_flags.add(flag)
					tokens.append("-"+flag+default)
				else:
					enabled_flags.add(flag)
					tokens.append(flag+default)
			elif operator == "!?":
				if flag not in use:
					disabled_flags.add(flag)
					tokens.append("-"+flag+default)
			else:
				tokens.append(x)

		return _use_dep(tokens, self.eapi, enabled_flags=enabled_flags, disabled_flags=disabled_flags, \
			missing_enabled=self.missing_enabled, missing_disabled=self.missing_disabled, required=self.required)

	def violated_conditionals(self, other_use, is_valid_flag, parent_use=None):
		"""
		Create a new instance with satisfied use deps removed.
		"""
		if parent_use is None and self.conditional:
			raise InvalidAtom("violated_conditionals needs 'parent_use'" + \
				" parameter for conditional flags.")

		enabled_flags = set()
		disabled_flags = set()

		conditional = {}
		tokens = []

		all_defaults = frozenset(chain(self.missing_enabled, self.missing_disabled))
		
		def validate_flag(flag):
			return is_valid_flag(flag) or flag in all_defaults

		usedep_re = _get_usedep_re(self.eapi)

		for x in self.tokens:
			m = usedep_re.match(x)

			operator = m.group("prefix") + m.group("suffix")
			flag = m.group("flag")

			if not validate_flag(flag):
				tokens.append(x)
				if not operator:
					enabled_flags.add(flag)
				elif operator == "-":
					disabled_flags.add(flag)
				elif operator == "?":
					conditional.setdefault("enabled", set()).add(flag)
				elif operator == "=":
					conditional.setdefault("equal", set()).add(flag)
				elif operator == "!=":
					conditional.setdefault("not_equal", set()).add(flag)
				elif operator == "!?":
					conditional.setdefault("disabled", set()).add(flag)

				continue

			if not operator:
				if flag not in other_use:
					if is_valid_flag(flag) or flag in self.missing_disabled:
						tokens.append(x)
						enabled_flags.add(flag)
			elif operator == "-":
				if flag not in other_use:
					if not is_valid_flag(flag):
						if flag in self.missing_enabled:
							tokens.append(x)
							disabled_flags.add(flag)
				else:
					tokens.append(x)
					disabled_flags.add(flag)
			elif operator == "?":
				if flag not in parent_use or flag in other_use:
					continue

				if is_valid_flag(flag) or flag in self.missing_disabled:
					tokens.append(x)
					conditional.setdefault("enabled", set()).add(flag)
			elif operator == "=":
				if flag in parent_use and flag not in other_use:
					if is_valid_flag(flag):
						tokens.append(x)
						conditional.setdefault("equal", set()).add(flag)
					else:
						if flag in self.missing_disabled:
							tokens.append(x)
							conditional.setdefault("equal", set()).add(flag)
				elif flag not in parent_use:
					if flag not in other_use:
						if not is_valid_flag(flag):
							if flag in self.missing_enabled:
								tokens.append(x)
								conditional.setdefault("equal", set()).add(flag)
					else:
						tokens.append(x)
						conditional.setdefault("equal", set()).add(flag)
			elif operator == "!=":
				if flag not in parent_use and flag not in other_use:
					if is_valid_flag(flag):
						tokens.append(x)
						conditional.setdefault("not_equal", set()).add(flag)
					else:
						if flag in self.missing_disabled:
							tokens.append(x)
							conditional.setdefault("not_equal", set()).add(flag)
				elif flag in parent_use:
					if flag not in other_use:
						if not is_valid_flag(flag):
							if flag in self.missing_enabled:
								tokens.append(x)
								conditional.setdefault("not_equal", set()).add(flag)
					else:
						tokens.append(x)
						conditional.setdefault("not_equal", set()).add(flag)
			elif operator == "!?":
				if flag not in parent_use:
					if flag not in other_use:
						if not is_valid_flag(flag) and flag in self.missing_enabled:
							tokens.append(x)
							conditional.setdefault("disabled", set()).add(flag)
					else:
						tokens.append(x)
						conditional.setdefault("disabled", set()).add(flag)

		return _use_dep(tokens, self.eapi, enabled_flags=enabled_flags, disabled_flags=disabled_flags, \
			missing_enabled=self.missing_enabled, missing_disabled=self.missing_disabled, \
			conditional=conditional, required=self.required)

	def _eval_qa_conditionals(self, use_mask, use_force):
		"""
		For repoman, evaluate all possible combinations within the constraints
		of the given use.force and use.mask settings. The result may seem
		ambiguous in the sense that the same flag can be in both the enabled
		and disabled sets, but this is useful within the context of how its
		intended to be used by repoman. It is assumed that the caller has
		already ensured that there is no intersection between the given
		use_mask and use_force sets when necessary.
		"""
		enabled_flags = set(self.enabled)
		disabled_flags = set(self.disabled)
		missing_enabled = self.missing_enabled
		missing_disabled = self.missing_disabled

		tokens = []
		usedep_re = _get_usedep_re(self.eapi)

		for x in self.tokens:
			m = usedep_re.match(x)

			operator = m.group("prefix") + m.group("suffix")
			flag = m.group("flag")
			default = m.group("default")
			if default is None:
				default = ""

			if operator == "?":
				if flag not in use_mask:
					enabled_flags.add(flag)
					tokens.append(flag+default)
			elif operator == "=":
				if flag not in use_mask:
					enabled_flags.add(flag)
					tokens.append(flag+default)
				if flag not in use_force:
					disabled_flags.add(flag)
					tokens.append("-"+flag+default)
			elif operator == "!=":
				if flag not in use_force:
					enabled_flags.add(flag)
					tokens.append(flag+default)
				if flag not in use_mask:
					disabled_flags.add(flag)
					tokens.append("-"+flag+default)
			elif operator == "!?":
				if flag not in use_force:
					disabled_flags.add(flag)
					tokens.append("-"+flag+default)
			else:
				tokens.append(x)

		return _use_dep(tokens, self.eapi, enabled_flags=enabled_flags, disabled_flags=disabled_flags, \
			missing_enabled=missing_enabled, missing_disabled=missing_disabled, required=self.required)

if sys.hexversion < 0x3000000:
	_atom_base = unicode
else:
	_atom_base = str

class Atom(_atom_base):

	"""
	For compatibility with existing atom string manipulation code, this
	class emulates most of the str methods that are useful with atoms.
	"""

	class _blocker(object):
		__slots__ = ("overlap",)

		class _overlap(object):
			__slots__ = ("forbid",)

			def __init__(self, forbid=False):
				self.forbid = forbid

		def __init__(self, forbid_overlap=False):
			self.overlap = self._overlap(forbid=forbid_overlap)

	def __new__(cls, s, unevaluated_atom=None, allow_wildcard=False, allow_repo=False,
		_use=None, eapi=None, is_valid_flag=None):
		return _atom_base.__new__(cls, s)

	def __init__(self, s, unevaluated_atom=None, allow_wildcard=False, allow_repo=False,
		_use=None, eapi=None, is_valid_flag=None):
		if isinstance(s, Atom):
			# This is an efficiency assertion, to ensure that the Atom
			# constructor is not called redundantly.
			raise TypeError(_("Expected %s, got %s") % \
				(_atom_base, type(s)))

		_atom_base.__init__(s)

		if "!" == s[:1]:
			blocker = self._blocker(forbid_overlap=("!" == s[1:2]))
			if blocker.overlap.forbid:
				s = s[2:]
			else:
				s = s[1:]
		else:
			blocker = False
		self.__dict__['blocker'] = blocker
		m = _atom_re.match(s)
		extended_syntax = False
		if m is None:
			if allow_wildcard:
				m = _atom_wildcard_re.match(s)
				if m is None:
					raise InvalidAtom(self)
				op = None
				gdict = m.groupdict()
				cpv = cp = gdict['simple']
				if cpv.find("**") != -1:
					raise InvalidAtom(self)
				slot = gdict['slot']
				repo = gdict['repo']
				use_str = None
				extended_syntax = True
			else:
				raise InvalidAtom(self)
		elif m.group('op') is not None:
			base = _atom_re.groupindex['op']
			op = m.group(base + 1)
			cpv = m.group(base + 2)
			cp = m.group(base + 3)
			slot = m.group(_atom_re.groups - 2)
			repo = m.group(_atom_re.groups - 1)
			use_str = m.group(_atom_re.groups)
			if m.group(base + 4) is not None:
				raise InvalidAtom(self)
		elif m.group('star') is not None:
			base = _atom_re.groupindex['star']
			op = '=*'
			cpv = m.group(base + 1)
			cp = m.group(base + 2)
			slot = m.group(_atom_re.groups - 2)
			repo = m.group(_atom_re.groups - 1)
			use_str = m.group(_atom_re.groups)
			if m.group(base + 3) is not None:
				raise InvalidAtom(self)
		elif m.group('simple') is not None:
			op = None
			cpv = cp = m.group(_atom_re.groupindex['simple'] + 1)
			slot = m.group(_atom_re.groups - 2)
			repo = m.group(_atom_re.groups - 1)
			use_str = m.group(_atom_re.groups)
			if m.group(_atom_re.groupindex['simple'] + 2) is not None:
				raise InvalidAtom(self)

		else:
			raise AssertionError(_("required group not found in atom: '%s'") % self)
		self.__dict__['cp'] = cp
		self.__dict__['cpv'] = cpv
		self.__dict__['repo'] = repo
		self.__dict__['slot'] = slot
		self.__dict__['operator'] = op
		self.__dict__['extended_syntax'] = extended_syntax

		if not (repo is None or allow_repo):
			raise InvalidAtom(self)

		if use_str is not None:
			if _use is not None:
				use = _use
			else:
				use = _use_dep(use_str[1:-1].split(","), eapi)
			without_use = Atom(m.group('without_use'), allow_repo=allow_repo)
		else:
			use = None
			if unevaluated_atom is not None and \
				unevaluated_atom.use is not None:
				# unevaluated_atom.use is used for IUSE checks when matching
				# packages, so it must not propagate to without_use
				without_use = Atom(s, allow_wildcard=allow_wildcard,
					allow_repo=allow_repo)
			else:
				without_use = self

		self.__dict__['use'] = use
		self.__dict__['without_use'] = without_use

		if unevaluated_atom:
			self.__dict__['unevaluated_atom'] = unevaluated_atom
		else:
			self.__dict__['unevaluated_atom'] = self

		if eapi is not None:
			if not isinstance(eapi, basestring):
				raise TypeError('expected eapi argument of ' + \
					'%s, got %s: %s' % (basestring, type(eapi), eapi,))
			if self.slot and not eapi_has_slot_deps(eapi):
				raise InvalidAtom(
					_("Slot deps are not allowed in EAPI %s: '%s'") \
					% (eapi, self), category='EAPI.incompatible')
			if self.use:
				if not eapi_has_use_deps(eapi):
					raise InvalidAtom(
						_("Use deps are not allowed in EAPI %s: '%s'") \
						% (eapi, self), category='EAPI.incompatible')
				elif not eapi_has_use_dep_defaults(eapi) and \
					(self.use.missing_enabled or self.use.missing_disabled):
					raise InvalidAtom(
						_("Use dep defaults are not allowed in EAPI %s: '%s'") \
						% (eapi, self), category='EAPI.incompatible')
				if is_valid_flag is not None and self.use.conditional:
					invalid_flag = None
					try:
						for conditional_type, flags in \
							self.use.conditional.items():
							for flag in flags:
								if not is_valid_flag(flag):
									invalid_flag = (conditional_type, flag)
									raise StopIteration()
					except StopIteration:
						pass
					if invalid_flag is not None:
						conditional_type, flag = invalid_flag
						conditional_str = _use_dep._conditional_strings[conditional_type]
						msg = _("USE flag '%s' referenced in " + \
							"conditional '%s' in atom '%s' is not in IUSE") \
							% (flag, conditional_str % flag, self)
						raise InvalidAtom(msg, category='IUSE.missing')
			if self.blocker and self.blocker.overlap.forbid and not eapi_has_strong_blocks(eapi):
				raise InvalidAtom(
					_("Strong blocks are not allowed in EAPI %s: '%s'") \
						% (eapi, self), category='EAPI.incompatible')

	@property
	def without_repo(self):
		if self.repo is None:
			return self
		return Atom(self.replace(_repo_separator + self.repo, '', 1),
			allow_wildcard=True)

	@property
	def without_slot(self):
		if self.slot is None:
			return self
		return Atom(self.replace(_slot_separator + self.slot, '', 1),
			allow_repo=True, allow_wildcard=True)

	def __setattr__(self, name, value):
		raise AttributeError("Atom instances are immutable",
			self.__class__, name, value)

	def intersects(self, other):
		"""
		Atoms with different cpv, operator or use attributes cause this method
		to return False even though there may actually be some intersection.
		TODO: Detect more forms of intersection.
		@param other: The package atom to match
		@type other: Atom
		@rtype: Boolean
		@return: True if this atom and the other atom intersect,
			False otherwise.
		"""
		if not isinstance(other, Atom):
			raise TypeError("expected %s, got %s" % \
				(Atom, type(other)))

		if self == other:
			return True

		if self.cp != other.cp or \
			self.use != other.use or \
			self.operator != other.operator or \
			self.cpv != other.cpv:
			return False

		if self.slot is None or \
			other.slot is None or \
			self.slot == other.slot:
			return True

		return False

	def evaluate_conditionals(self, use):
		"""
		Create an atom instance with any USE conditionals evaluated.
		@param use: The set of enabled USE flags
		@type use: set
		@rtype: Atom
		@return: an atom instance with any USE conditionals evaluated
		"""
		if not (self.use and self.use.conditional):
			return self
		atom = remove_slot(self)
		if self.slot:
			atom += ":%s" % self.slot
		use_dep = self.use.evaluate_conditionals(use)
		atom += str(use_dep)
		return Atom(atom, unevaluated_atom=self, allow_repo=(self.repo is not None), _use=use_dep)

	def violated_conditionals(self, other_use, is_valid_flag, parent_use=None):
		"""
		Create an atom instance with any USE conditional removed, that is
		satisfied by other_use.
		@param other_use: The set of enabled USE flags
		@type other_use: set
		@param is_valid_flag: Function that decides if a use flag is referenceable in use deps
		@type is_valid_flag: function
		@param parent_use: Set of enabled use flags of the package requiring this atom
		@type parent_use: set
		@rtype: Atom
		@return: an atom instance with any satisfied USE conditionals removed
		"""
		if not self.use:
			return self
		atom = remove_slot(self)
		if self.slot:
			atom += ":%s" % self.slot
		use_dep = self.use.violated_conditionals(other_use, is_valid_flag, parent_use)
		atom += str(use_dep)
		return Atom(atom, unevaluated_atom=self, allow_repo=(self.repo is not None), _use=use_dep)

	def _eval_qa_conditionals(self, use_mask, use_force):
		if not (self.use and self.use.conditional):
			return self
		atom = remove_slot(self)
		if self.slot:
			atom += ":%s" % self.slot
		use_dep = self.use._eval_qa_conditionals(use_mask, use_force)
		atom += str(use_dep)
		return Atom(atom, unevaluated_atom=self, allow_repo=(self.repo is not None), _use=use_dep)

	def __copy__(self):
		"""Immutable, so returns self."""
		return self

	def __deepcopy__(self, memo=None):
		"""Immutable, so returns self."""
		memo[id(self)] = self
		return self

_extended_cp_re_cache = {}

def extended_cp_match(extended_cp, other_cp):
	"""
	Checks if an extended syntax cp matches a non extended cp
	"""
	# Escape special '+' and '.' characters which are allowed in atoms,
	# and convert '*' to regex equivalent.
	global _extended_cp_re_cache
	extended_cp_re = _extended_cp_re_cache.get(extended_cp)
	if extended_cp_re is None:
		extended_cp_re = re.compile("^" + re.escape(extended_cp).replace(
			r'\*', '[^/]*') + "$")
		_extended_cp_re_cache[extended_cp] = extended_cp_re
	return extended_cp_re.match(other_cp) is not None

class ExtendedAtomDict(portage.cache.mappings.MutableMapping):
	"""
	dict() wrapper that supports extended atoms as keys and allows lookup
	of a normal cp against other normal cp and extended cp.
	The value type has to be given to __init__ and is assumed to be the same
	for all values.
	"""

	__slots__ = ('_extended', '_normal', '_value_class')

	def __init__(self, value_class):
		self._extended = {}
		self._normal = {}
		self._value_class = value_class

	def copy(self):
		result = self.__class__(self._value_class)
		result._extended.update(self._extended)
		result._normal.update(self._normal)
		return result

	def __iter__(self):
		for k in self._normal:
			yield k
		for k in self._extended:
			yield k

	def iteritems(self):
		for item in self._normal.items():
			yield item
		for item in self._extended.items():
			yield item

	def __delitem__(self, cp):
		if "*" in cp:
			return self._extended.__delitem__(cp)
		else:
			return self._normal.__delitem__(cp)

	if sys.hexversion >= 0x3000000:
		keys = __iter__
		items = iteritems

	def __len__(self):
		return len(self._normal) + len(self._extended)

	def setdefault(self, cp, default=None):
		if "*" in cp:
			return self._extended.setdefault(cp, default)
		else:
			return self._normal.setdefault(cp, default)

	def __getitem__(self, cp):

		if not isinstance(cp, basestring):
			raise KeyError(cp)

		if '*' in cp:
			return self._extended[cp]

		ret = self._value_class()
		normal_match = self._normal.get(cp)
		match = False

		if normal_match is not None:
			match = True
			if hasattr(ret, "update"):
				ret.update(normal_match)
			elif hasattr(ret, "extend"):
				ret.extend(normal_match)
			else:
				raise NotImplementedError()

		for extended_cp in self._extended:
			if extended_cp_match(extended_cp, cp):
				match = True
				if hasattr(ret, "update"):
					ret.update(self._extended[extended_cp])
				elif hasattr(ret, "extend"):
					ret.extend(self._extended[extended_cp])
				else:
					raise NotImplementedError()

		if not match:
			raise KeyError(cp)

		return ret

	def __setitem__(self, cp, val):
		if "*" in cp:
			self._extended[cp] = val
		else:
			self._normal[cp] = val

	def __eq__(self, other):
		return self._value_class == other._value_class and \
			self._extended == other._extended and \
			self._normal == other._normal

	def clear(self):
		self._extended.clear()
		self._normal.clear()


def get_operator(mydep):
	"""
	Return the operator used in a depstring.

	Example usage:
		>>> from portage.dep import *
		>>> get_operator(">=test-1.0")
		'>='

	@param mydep: The dep string to check
	@type mydep: String
	@rtype: String
	@return: The operator. One of:
		'~', '=', '>', '<', '=*', '>=', or '<='
	"""
	if not isinstance(mydep, Atom):
		mydep = Atom(mydep)

	return mydep.operator

def dep_getcpv(mydep):
	"""
	Return the category-package-version with any operators/slot specifications stripped off

	Example usage:
		>>> dep_getcpv('>=media-libs/test-3.0')
		'media-libs/test-3.0'

	@param mydep: The depstring
	@type mydep: String
	@rtype: String
	@return: The depstring with the operator removed
	"""
	if not isinstance(mydep, Atom):
		mydep = Atom(mydep)

	return mydep.cpv

def dep_getslot(mydep):
	"""
	Retrieve the slot on a depend.

	Example usage:
		>>> dep_getslot('app-misc/test:3')
		'3'

	@param mydep: The depstring to retrieve the slot of
	@type mydep: String
	@rtype: String
	@return: The slot
	"""
	slot = getattr(mydep, "slot", False)
	if slot is not False:
		return slot

	#remove repo_name if present
	mydep = mydep.split(_repo_separator)[0]
	
	colon = mydep.find(_slot_separator)
	if colon != -1:
		bracket = mydep.find("[", colon)
		if bracket == -1:
			return mydep[colon+1:]
		else:
			return mydep[colon+1:bracket]
	return None

def dep_getrepo(mydep):
	"""
	Retrieve the repo on a depend.

	Example usage:
		>>> dep_getrepo('app-misc/test::repository')
		'repository'

	@param mydep: The depstring to retrieve the repository of
	@type mydep: String
	@rtype: String
	@return: The repository name
	"""
	repo = getattr(mydep, "repo", False)
	if repo is not False:
		return repo

	metadata = getattr(mydep, "metadata", False)
	if metadata:
		repo = metadata.get('repository', False)
		if repo is not False:
			return repo

	colon = mydep.find(_repo_separator)
	if colon != -1:
		bracket = mydep.find("[", colon)
		if bracket == -1:
			return mydep[colon+2:]
		else:
			return mydep[colon+2:bracket]
	return None
def remove_slot(mydep):
	"""
	Removes dep components from the right side of an atom:
		* slot
		* use
		* repo
	And repo_name from the left side.
	"""
	colon = mydep.find(_slot_separator)
	if colon != -1:
		mydep = mydep[:colon]
	else:
		bracket = mydep.find("[")
		if bracket != -1:
			mydep = mydep[:bracket]
	return mydep

def dep_getusedeps( depend ):
	"""
	Pull a listing of USE Dependencies out of a dep atom.
	
	Example usage:
		>>> dep_getusedeps('app-misc/test:3[foo,-bar]')
		('foo', '-bar')
	
	@param depend: The depstring to process
	@type depend: String
	@rtype: List
	@return: List of use flags ( or [] if no flags exist )
	"""
	use_list = []
	open_bracket = depend.find('[')
	# -1 = failure (think c++ string::npos)
	comma_separated = False
	bracket_count = 0
	while( open_bracket != -1 ):
		bracket_count += 1
		if bracket_count > 1:
			raise InvalidAtom(_("USE Dependency with more "
				"than one set of brackets: %s") % (depend,))
		close_bracket = depend.find(']', open_bracket )
		if close_bracket == -1:
			raise InvalidAtom(_("USE Dependency with no closing bracket: %s") % depend )
		use = depend[open_bracket + 1: close_bracket]
		# foo[1:1] may return '' instead of None, we don't want '' in the result
		if not use:
			raise InvalidAtom(_("USE Dependency with "
				"no use flag ([]): %s") % depend )
		if not comma_separated:
			comma_separated = "," in use

		if comma_separated and bracket_count > 1:
			raise InvalidAtom(_("USE Dependency contains a mixture of "
				"comma and bracket separators: %s") % depend )

		if comma_separated:
			for x in use.split(","):
				if x:
					use_list.append(x)
				else:
					raise InvalidAtom(_("USE Dependency with no use "
						"flag next to comma: %s") % depend )
		else:
			use_list.append(use)

		# Find next use flag
		open_bracket = depend.find( '[', open_bracket+1 )
	return tuple(use_list)

# \w is [a-zA-Z0-9_]

# 2.1.3 A slot name may contain any of the characters [A-Za-z0-9+_.-].
# It must not begin with a hyphen or a dot.
_slot_separator = ":"
_slot = r'([\w+][\w+.-]*)'
_slot_re = re.compile('^' + _slot + '$', re.VERBOSE)

_use = r'\[.*\]'
_op = r'([=~]|[><]=?)'
_repo_separator = "::"
_repo_name = r'[\w][\w-]*'
_repo = r'(?:' + _repo_separator + '(' + _repo_name + ')' + ')?'

_atom_re = re.compile('^(?P<without_use>(?:' +
	'(?P<op>' + _op + _cpv + ')|' +
	'(?P<star>=' + _cpv + r'\*)|' +
	'(?P<simple>' + _cp + '))' + 
	'(' + _slot_separator + _slot + ')?' + _repo + ')(' + _use + ')?$', re.VERBOSE)
	
_extended_cat = r'[\w+*][\w+.*-]*'
_extended_pkg = r'[\w+*][\w+*-]*?'

_atom_wildcard_re = re.compile('(?P<simple>(' + _extended_cat + ')/(' + _extended_pkg + '))(:(?P<slot>' + _slot + '))?(' + _repo_separator + '(?P<repo>' + _repo_name + '))?$')

_useflag_re = {
	"0": re.compile(r'^[A-Za-z0-9][A-Za-z0-9+_@-]*$'),
#	"5": re.compile(r'^[A-Za-z0-9][A-Za-z0-9+_@.-]*$'),
}

def _get_useflag_re(eapi):
	return _useflag_re["0"]
#	if eapi in ("0", "1", "2", "3_pre1", "3_pre2", "3", "4_pre1", "4"):
#		return _useflag_re["0"]
#	else:
#		return _useflag_re["5"]

def isvalidatom(atom, allow_blockers=False, allow_wildcard=False, allow_repo=False):
	"""
	Check to see if a depend atom is valid

	Example usage:
		>>> isvalidatom('media-libs/test-3.0')
		False
		>>> isvalidatom('>=media-libs/test-3.0')
		True

	@param atom: The depend atom to check against
	@type atom: String or Atom
	@rtype: Boolean
	@return: One of the following:
		1) False if the atom is invalid
		2) True if the atom is valid
	"""
	try:
		if not isinstance(atom, Atom):
			atom = Atom(atom, allow_wildcard=allow_wildcard, allow_repo=allow_repo)
		if not allow_blockers and atom.blocker:
			return False
		return True
	except InvalidAtom:
		return False

def isjustname(mypkg):
	"""
	Checks to see if the atom is only the package name (no version parts).

	Example usage:
		>>> isjustname('=media-libs/test-3.0')
		False
		>>> isjustname('media-libs/test')
		True

	@param mypkg: The package atom to check
	@param mypkg: String or Atom
	@rtype: Integer
	@return: One of the following:
		1) False if the package string is not just the package name
		2) True if it is
	"""
	try:
		if not isinstance(mypkg, Atom):
			mypkg = Atom(mypkg)
		return mypkg == mypkg.cp
	except InvalidAtom:
		pass

	for x in mypkg.split('-')[-2:]:
		if ververify(x):
			return False
	return True

def isspecific(mypkg):
	"""
	Checks to see if a package is in =category/package-version or
	package-version format.

	Example usage:
		>>> isspecific('media-libs/test')
		False
		>>> isspecific('=media-libs/test-3.0')
		True

	@param mypkg: The package depstring to check against
	@type mypkg: String
	@rtype: Boolean
	@return: One of the following:
		1) False if the package string is not specific
		2) True if it is
	"""
	try:
		if not isinstance(mypkg, Atom):
			mypkg = Atom(mypkg)
		return mypkg != mypkg.cp
	except InvalidAtom:
		pass

	# Fall back to legacy code for backward compatibility.
	return not isjustname(mypkg)

def dep_getkey(mydep):
	"""
	Return the category/package-name of a depstring.

	Example usage:
		>>> dep_getkey('=media-libs/test-3.0')
		'media-libs/test'

	@param mydep: The depstring to retrieve the category/package-name of
	@type mydep: String
	@rtype: String
	@return: The package category/package-name
	"""
	if not isinstance(mydep, Atom):
		mydep = Atom(mydep, allow_wildcard=True, allow_repo=True)

	return mydep.cp

def match_to_list(mypkg, mylist):
	"""
	Searches list for entries that matches the package.

	@param mypkg: The package atom to match
	@type mypkg: String
	@param mylist: The list of package atoms to compare against
	@param mylist: List
	@rtype: List
	@return: A unique list of package atoms that match the given package atom
	"""
	return [ x for x in set(mylist) if match_from_list(x, [mypkg]) ]

def best_match_to_list(mypkg, mylist):
	"""
	Returns the most specific entry that matches the package given.

	@param mypkg: The package atom to check
	@type mypkg: String
	@param mylist: The list of package atoms to check against
	@type mylist: List
	@rtype: String
	@return: The package atom which best matches given the following ordering:
		- =cpv      6
		- ~cpv      5
		- =cpv*     4
		- cp:slot   3
		- >cpv      2
		- <cpv      2
		- >=cpv     2
		- <=cpv     2
		- cp        1
		- cp:slot with extended syntax	0
		- cp with extended syntax	-1
	"""
	operator_values = {'=':6, '~':5, '=*':4,
		'>':2, '<':2, '>=':2, '<=':2, None:1}
	maxvalue = -2
	bestm  = None
	for x in match_to_list(mypkg, mylist):
		if x.extended_syntax:
			if dep_getslot(x) is not None:
				if maxvalue < 0:
					maxvalue = 0
					bestm = x
			else:
				if maxvalue < -1:
					maxvalue = -1
					bestm = x
			continue
		if dep_getslot(x) is not None:
			if maxvalue < 3:
				maxvalue = 3
				bestm = x
		op_val = operator_values[x.operator]
		if op_val > maxvalue:
			maxvalue = op_val
			bestm  = x
	return bestm

def match_from_list(mydep, candidate_list):
	"""
	Searches list for entries that matches the package.

	@param mydep: The package atom to match
	@type mydep: String
	@param candidate_list: The list of package atoms to compare against
	@param candidate_list: List
	@rtype: List
	@return: A list of package atoms that match the given package atom
	"""

	if not candidate_list:
		return []

	from portage.util import writemsg
	if "!" == mydep[:1]:
		if "!" == mydep[1:2]:
			mydep = mydep[2:]
		else:
			mydep = mydep[1:]
	if not isinstance(mydep, Atom):
		mydep = Atom(mydep, allow_wildcard=True, allow_repo=True)

	mycpv     = mydep.cpv
	mycpv_cps = catpkgsplit(mycpv) # Can be None if not specific
	slot      = mydep.slot

	if not mycpv_cps:
		cat, pkg = catsplit(mycpv)
		ver      = None
		rev      = None
	else:
		cat, pkg, ver, rev = mycpv_cps
		if mydep == mycpv:
			raise KeyError(_("Specific key requires an operator"
				" (%s) (try adding an '=')") % (mydep))

	if ver and rev:
		operator = mydep.operator
		if not operator:
			writemsg(_("!!! Invalid atom: %s\n") % mydep, noiselevel=-1)
			return []
	else:
		operator = None

	mylist = []

	if operator is None:
		for x in candidate_list:
			cp = getattr(x, "cp", None)
			if cp is None:
				mysplit = catpkgsplit(remove_slot(x))
				if mysplit is not None:
					cp = mysplit[0] + '/' + mysplit[1]

			if cp is None:
				continue

			if cp == mycpv or (mydep.extended_syntax and \
				extended_cp_match(mydep.cp, cp)):
				mylist.append(x)

	elif operator == "=": # Exact match
		for x in candidate_list:
			xcpv = getattr(x, "cpv", None)
			if xcpv is None:
				xcpv = remove_slot(x)
			if not cpvequal(xcpv, mycpv):
				continue
			mylist.append(x)

	elif operator == "=*": # glob match
		# XXX: Nasty special casing for leading zeros
		# Required as =* is a literal prefix match, so can't 
		# use vercmp
		mysplit = catpkgsplit(mycpv)
		myver = mysplit[2].lstrip("0")
		if not myver or not myver[0].isdigit():
			myver = "0"+myver
		mycpv = mysplit[0]+"/"+mysplit[1]+"-"+myver
		for x in candidate_list:
			xs = getattr(x, "cpv_split", None)
			if xs is None:
				xs = catpkgsplit(remove_slot(x))
			myver = xs[2].lstrip("0")
			if not myver or not myver[0].isdigit():
				myver = "0"+myver
			xcpv = xs[0]+"/"+xs[1]+"-"+myver
			if xcpv.startswith(mycpv):
				mylist.append(x)

	elif operator == "~": # version, any revision, match
		for x in candidate_list:
			xs = getattr(x, "cpv_split", None)
			if xs is None:
				xs = catpkgsplit(remove_slot(x))
			if xs is None:
				raise InvalidData(x)
			if not cpvequal(xs[0]+"/"+xs[1]+"-"+xs[2], mycpv_cps[0]+"/"+mycpv_cps[1]+"-"+mycpv_cps[2]):
				continue
			if xs[2] != ver:
				continue
			mylist.append(x)

	elif operator in [">", ">=", "<", "<="]:
		mysplit = ["%s/%s" % (cat, pkg), ver, rev]
		for x in candidate_list:
			xs = getattr(x, "cpv_split", None)
			if xs is None:
				xs = catpkgsplit(remove_slot(x))
			xcat, xpkg, xver, xrev = xs
			xs = ["%s/%s" % (xcat, xpkg), xver, xrev]
			try:
				result = pkgcmp(xs, mysplit)
			except ValueError: # pkgcmp may return ValueError during int() conversion
				writemsg(_("\nInvalid package name: %s\n") % x, noiselevel=-1)
				raise
			if result is None:
				continue
			elif operator == ">":
				if result > 0:
					mylist.append(x)
			elif operator == ">=":
				if result >= 0:
					mylist.append(x)
			elif operator == "<":
				if result < 0:
					mylist.append(x)
			elif operator == "<=":
				if result <= 0:
					mylist.append(x)
			else:
				raise KeyError(_("Unknown operator: %s") % mydep)
	else:
		raise KeyError(_("Unknown operator: %s") % mydep)

	if slot is not None and not mydep.extended_syntax:
		candidate_list = mylist
		mylist = []
		for x in candidate_list:
			xslot = getattr(x, "slot", False)
			if xslot is False:
				xslot = dep_getslot(x)
			if xslot is not None and xslot != slot:
				continue
			mylist.append(x)

	if mydep.unevaluated_atom.use:
		candidate_list = mylist
		mylist = []
		for x in candidate_list:
			use = getattr(x, "use", None)
			if use is not None:
				if mydep.unevaluated_atom.use and \
					not x.iuse.is_valid_flag(
					mydep.unevaluated_atom.use.required):
					continue

				if mydep.use:

					missing_enabled = mydep.use.missing_enabled.difference(x.iuse.all)
					missing_disabled = mydep.use.missing_disabled.difference(x.iuse.all)

					if mydep.use.enabled:
						if mydep.use.enabled.intersection(missing_disabled):
							continue
						need_enabled = mydep.use.enabled.difference(use.enabled)
						if need_enabled:
							need_enabled = need_enabled.difference(missing_enabled)
							if need_enabled:
								continue

					if mydep.use.disabled:
						if mydep.use.disabled.intersection(missing_enabled):
							continue
						need_disabled = mydep.use.disabled.intersection(use.enabled)
						if need_disabled:
							need_disabled = need_disabled.difference(missing_disabled)
							if need_disabled:
								continue

			mylist.append(x)

	if mydep.repo:
		candidate_list = mylist
		mylist = []
		for x in candidate_list:
			repo = getattr(x, "repo", False)
			if repo is False:
				repo = dep_getrepo(x)
			if repo is not None and repo != mydep.repo:
				continue
			mylist.append(x)

	return mylist

def human_readable_required_use(required_use):
	return required_use.replace("^^", "exactly-one-of").replace("||", "any-of")

def get_required_use_flags(required_use):
	"""
	Returns a set of use flags that are used in the given REQUIRED_USE string

	@param required_use: REQUIRED_USE string
	@type required_use: String
	@rtype: Set
	@return: Set of use flags that are used in the given REQUIRED_USE string
	"""

	mysplit = required_use.split()
	level = 0
	stack = [[]]
	need_bracket = False

	used_flags = set()

	def register_token(token):
		if token.endswith("?"):
			token = token[:-1]
		if token.startswith("!"):
			token = token[1:]
		used_flags.add(token)

	for token in mysplit:
		if token == "(":
			need_bracket = False
			stack.append([])
			level += 1
		elif token == ")":
			if need_bracket:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % required_use)
			if level > 0:
				level -= 1
				l = stack.pop()
				ignore = False
				if stack[level]:
					if stack[level][-1] in ("||", "^^") or \
						(not isinstance(stack[level][-1], bool) and \
						stack[level][-1][-1] == "?"):
						ignore = True
						stack[level].pop()
						stack[level].append(True)

				if l and not ignore:
					stack[level].append(all(x for x in l))
			else:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % required_use)
		elif token in ("||", "^^"):
			if need_bracket:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % required_use)
			need_bracket = True
			stack[level].append(token)
		else:
			if need_bracket or "(" in token or ")" in token or \
				"|" in token or "^" in token:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % required_use)

			if token[-1] == "?":
				need_bracket = True
				stack[level].append(token)
			else:
				stack[level].append(True)
			
			register_token(token)

	if level != 0 or need_bracket:
		raise InvalidDependString(
			_("malformed syntax: '%s'") % required_use)

	return frozenset(used_flags)

class _RequiredUseLeaf(object):

	__slots__ = ('_satisfied', '_token')

	def __init__(self, token, satisfied):
		self._token = token
		self._satisfied = satisfied

	def tounicode(self):
		return self._token

class _RequiredUseBranch(object):

	__slots__ = ('_children', '_operator', '_parent', '_satisfied')

	def __init__(self, operator=None, parent=None):
		self._children = []
		self._operator = operator
		self._parent = parent
		self._satisfied = False

	def __bool__(self):
		return self._satisfied

	def tounicode(self):

		include_parens = self._parent is not None
		tokens = []
		if self._operator is not None:
			tokens.append(self._operator)

		if include_parens:
			tokens.append("(")

		complex_nesting = False
		node = self
		while node != None and not complex_nesting:
			if node._operator in ("||", "^^"):
				complex_nesting = True
			else:
				node = node._parent

		if complex_nesting:
			for child in self._children:
				tokens.append(child.tounicode())
		else:
			for child in self._children:
				if not child._satisfied:
					tokens.append(child.tounicode())

		if include_parens:
			tokens.append(")")

		return " ".join(tokens)

	if sys.hexversion < 0x3000000:
		__nonzero__ = __bool__

def check_required_use(required_use, use, iuse_match):
	"""
	Checks if the use flags listed in 'use' satisfy all
	constraints specified in 'constraints'.

	@param required_use: REQUIRED_USE string
	@type required_use: String
	@param use: Enabled use flags
	@param use: List
	@param iuse_match: Callable that takes a single flag argument and returns
		True if the flag is matched, false otherwise,
	@param iuse_match: Callable
	@rtype: Bool
	@return: Indicates if REQUIRED_USE constraints are satisfied
	"""

	def is_active(token):
		if token.startswith("!"):
			flag = token[1:]
			is_negated = True
		else:
			flag = token
			is_negated = False

		if not flag or not iuse_match(flag):
			msg = _("USE flag '%s' is not in IUSE") \
				% (flag,)
			e = InvalidData(msg, category='IUSE.missing')
			raise InvalidDependString(msg, errors=(e,))

		return (flag in use and not is_negated) or \
			(flag not in use and is_negated)
	
	def is_satisfied(operator, argument):
		if not argument:
			#|| ( ) -> True
			return True

		if operator == "||":
			return (True in argument)
		elif operator == "^^":
			return (argument.count(True) == 1)
		elif operator[-1] == "?":
			return (False not in argument)

	mysplit = required_use.split()
	level = 0
	stack = [[]]
	tree = _RequiredUseBranch()
	node = tree
	need_bracket = False

	for token in mysplit:
		if token == "(":
			if not need_bracket:
				child = _RequiredUseBranch(parent=node)
				node._children.append(child)
				node = child

			need_bracket = False
			stack.append([])
			level += 1
		elif token == ")":
			if need_bracket:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % required_use)
			if level > 0:
				level -= 1
				l = stack.pop()
				op = None
				if stack[level]:
					if stack[level][-1] in ("||", "^^"):
						op = stack[level].pop()
						satisfied = is_satisfied(op, l)
						stack[level].append(satisfied)
						node._satisfied = satisfied

					elif not isinstance(stack[level][-1], bool) and \
						stack[level][-1][-1] == "?":
						op = stack[level].pop()
						if is_active(op[:-1]):
							satisfied = is_satisfied(op, l)
							stack[level].append(satisfied)
							node._satisfied = satisfied
						else:
							node._satisfied = True
							last_node = node._parent._children.pop()
							if last_node is not node:
								raise AssertionError(
									"node is not last child of parent")
							node = node._parent
							continue

				if op is None:
					satisfied = False not in l
					node._satisfied = satisfied
					if l:
						stack[level].append(satisfied)

					if len(node._children) <= 1 or \
						node._parent._operator not in ("||", "^^"):
						last_node = node._parent._children.pop()
						if last_node is not node:
							raise AssertionError(
								"node is not last child of parent")
						for child in node._children:
							node._parent._children.append(child)
							if isinstance(child, _RequiredUseBranch):
								child._parent = node._parent

				elif not node._children:
					last_node = node._parent._children.pop()
					if last_node is not node:
						raise AssertionError(
							"node is not last child of parent")

				elif len(node._children) == 1 and op in ("||", "^^"):
					last_node = node._parent._children.pop()
					if last_node is not node:
						raise AssertionError(
							"node is not last child of parent")
					node._parent._children.append(node._children[0])
					if isinstance(node._children[0], _RequiredUseBranch):
						node._children[0]._parent = node._parent
						node = node._children[0]
						if node._operator is None and \
							node._parent._operator not in ("||", "^^"):
							last_node = node._parent._children.pop()
							if last_node is not node:
								raise AssertionError(
									"node is not last child of parent")
							for child in node._children:
								node._parent._children.append(child)
								if isinstance(child, _RequiredUseBranch):
									child._parent = node._parent

				node = node._parent
			else:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % required_use)
		elif token in ("||", "^^"):
			if need_bracket:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % required_use)
			need_bracket = True
			stack[level].append(token)
			child = _RequiredUseBranch(operator=token, parent=node)
			node._children.append(child)
			node = child
		else:
			if need_bracket or "(" in token or ")" in token or \
				"|" in token or "^" in token:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % required_use)

			if token[-1] == "?":
				need_bracket = True
				stack[level].append(token)
				child = _RequiredUseBranch(operator=token, parent=node)
				node._children.append(child)
				node = child
			else:
				satisfied = is_active(token)
				stack[level].append(satisfied)
				node._children.append(_RequiredUseLeaf(token, satisfied))

	if level != 0 or need_bracket:
		raise InvalidDependString(
			_("malformed syntax: '%s'") % required_use)

	tree._satisfied = False not in stack[0]
	return tree

def extract_affecting_use(mystr, atom):
	"""
	Take a dep string and an atom and return the use flags
	that decide if the given atom is in effect.

	Example usage:
		>>> extract_use_cond('sasl? ( dev-libs/cyrus-sasl ) \
			!minimal? ( cxx? ( dev-libs/cyrus-sasl ) )', 'dev-libs/cyrus-sasl')
		(['sasl', 'minimal', 'cxx'])

	@param dep: The dependency string
	@type mystr: String
	@param atom: The atom to get into effect
	@type atom: String
	@rtype: Tuple of two lists of strings
	@return: List of use flags that need to be enabled, List of use flag that need to be disabled
	"""
	mysplit = mystr.split()
	level = 0
	stack = [[]]
	need_bracket = False
	affecting_use = set()

	def flag(conditional):
		if conditional[0] == "!":
			flag = conditional[1:-1]
		else:
			flag = conditional[:-1]

		if not flag:
			raise InvalidDependString(
				_("malformed syntax: '%s'") % mystr)

		return flag

	for token in mysplit:
		if token == "(":
			need_bracket = False
			stack.append([])
			level += 1
		elif token == ")":
			if need_bracket:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
			if level > 0:
				level -= 1
				l = stack.pop()
				is_single = (len(l) == 1 or (len(l)==2 and (l[0] == "||" or l[0][-1] == "?")))

				def ends_in_any_of_dep(k):
					return k>=0 and stack[k] and stack[k][-1] == "||"

				def ends_in_operator(k):
					return k>=0 and stack[k] and (stack[k][-1] == "||" or stack[k][-1][-1] == "?")

				def special_append():
					"""
					Use extend instead of append if possible. This kills all redundant brackets.
					"""
					if is_single and (not stack[level] or not stack[level][-1][-1] == "?"):
						if len(l) == 1 and isinstance(l[0], list):
							# l = [[...]]
							stack[level].extend(l[0])
						else:
							stack[level].extend(l)
					else:	
						stack[level].append(l)

				if l:
					if not ends_in_any_of_dep(level-1) and not ends_in_operator(level):
						#Optimize: ( ( ... ) ) -> ( ... ). Make sure there is no '||' hanging around.
						stack[level].extend(l)
					elif not stack[level]:
						#An '||' in the level above forces us to keep to brackets.
						special_append()
					elif len(l) == 1 and ends_in_any_of_dep(level):
						#Optimize: || ( A ) -> A
						stack[level].pop()
						special_append()
					elif len(l) == 2 and (l[0] == "||" or l[0][-1] == "?") and stack[level][-1] in (l[0], "||"):
						#Optimize: 	|| ( || ( ... ) ) -> || ( ... )
						#			foo? ( foo? ( ... ) ) -> foo? ( ... )
						#			|| ( foo? ( ... ) ) -> foo? ( ... )
						stack[level].pop()
						special_append()
						if l[0][-1] == "?":
							affecting_use.add(flag(l[0]))
					else:
						if stack[level] and stack[level][-1][-1] == "?":
							affecting_use.add(flag(stack[level][-1]))
						special_append()
				else:
					if stack[level] and (stack[level][-1] == "||" or stack[level][-1][-1] == "?"):
						stack[level].pop()
			else:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
		elif token == "||":
			if need_bracket:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
			need_bracket = True
			stack[level].append(token)
		else:
			if need_bracket or "(" in token or ")" in token or "|" in token:
				raise InvalidDependString(
					_("malformed syntax: '%s'") % mystr)

			if token[-1] == "?":
				need_bracket = True
				stack[level].append(token)
			elif token == atom:
				stack[level].append(token)

	if level != 0 or need_bracket:
		raise InvalidDependString(
			_("malformed syntax: '%s'") % mystr)

	return affecting_use
