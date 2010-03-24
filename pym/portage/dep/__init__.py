# deps.py -- Portage dependency resolution functions
# Copyright 2003-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = [
	'Atom', 'best_match_to_list', 'cpvequal',
	'dep_getcpv', 'dep_getkey', 'dep_getslot',
	'dep_getusedeps', 'dep_opconvert', 'flatten',
	'get_operator', 'isjustname', 'isspecific',
	'isvalidatom', 'match_from_list', 'match_to_list',
	'paren_enclose', 'paren_normalize', 'paren_reduce',
	'remove_slot', 'strip_empty', 'use_reduce'
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
from portage.exception import InvalidData, InvalidAtom
from portage.localization import _
from portage.versions import catpkgsplit, catsplit, \
	pkgcmp, pkgsplit, ververify, _cp, _cpv
import portage.cache.mappings

if sys.hexversion >= 0x3000000:
	basestring = str

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
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
			if level > 0:
				level -= 1
				l = stack.pop()
				if l:
					if not stack[level] or (stack[level][-1] != "||" and not stack[level][-1][-1] == "?"):
						#Optimize: ( ( ... ) ) -> ( ... )
						stack[level].extend(l)
					elif len(l) == 1 and stack[level][-1] == "||":
						#Optimize: || ( A ) -> A
						stack[level].pop()
						stack[level].extend(l)
					elif len(l) == 2 and (l[0] == "||" or l[0][-1] == "?") and stack[level][-1] in (l[0], "||"):
						#Optimize: 	|| ( || ( ... ) ) -> || ( ... )
						#			foo? ( foo? ( ... ) ) -> foo? ( ... )
						#			|| ( foo? ( ... ) ) -> foo? ( ... )
						stack[level].pop()
						stack[level].extend(l)
					else:
						stack[level].append(l)
				else:
					if stack[level] and (stack[level][-1] == "||" or stack[level][-1][-1] == "?"):
						stack[level].pop()
			else:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
		elif token == "||":
			if need_bracket:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
			need_bracket = True
			stack[level].append(token)
		else:
			if need_bracket or "(" in token or ")" in token or "|" in token:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % mystr)

			if token[-1] == "?":
				need_bracket = True
			
			stack[level].append(token)

	if level != 0 or need_bracket:
		raise portage.exception.InvalidDependString(
			_("malformed syntax: '%s'") % mystr)
	
	return stack[0]

class paren_normalize(list):
	"""Take a dependency structure as returned by paren_reduce or use_reduce
	and generate an equivalent structure that has no redundant lists."""
	def __init__(self, src):
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

def paren_enclose(mylist):
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
			mystrparts.append(x)
	return " ".join(mystrparts)

def use_reduce(depstr, uselist=[], masklist=[], matchall=False, excludeall=[], is_src_uri=False, \
	allow_src_uri_file_renames=False):
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
	@param matchall: List of flags for which negated conditionals are always treated as inactive.
	@type matchall: List
	@rtype: List
	@return: The use reduced depend array
	"""
	if isinstance(depstr, list):
		warnings.warn(_("Passing paren_reduced dep arrays to %s is deprecated. " + \
			"Pass the original dep string instead.") % \
			('portage.dep.use_reduce',), DeprecationWarning, stacklevel=2)
		depstr = paren_enclose(depstr)
	
	def is_active(conditional):
		if conditional.startswith("!"):
			flag = conditional[1:-1]
			is_negated = True
		else:
			flag = conditional[:-1]
			is_negated = False

		if not flag:
			raise portage.exception.InvalidDependString(
				_("malformed syntax: '%s'") % depstr)

		if is_negated and flag in excludeall:
			return False

		if flag in masklist:
			return is_negated

		if matchall:
			return True

		return (flag in uselist and not is_negated) or \
			(flag not in uselist and is_negated)

	mysplit = depstr.split()
	level = 0
	stack = [[]]
	need_bracket = False
	need_simple_token = False

	for token in mysplit:
		if token == "(":
			if need_simple_token:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % depstr)
			need_bracket = False
			stack.append([])
			level += 1
		elif token == ")":
			if need_bracket or need_simple_token:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % depstr)
			if level > 0:
				level -= 1
				l = stack.pop()
				ignore = False

				if stack[level]:
					if stack[level][-1] == "||" and not l:
						stack[level].pop()
					elif stack[level][-1][-1] == "?":
						if not is_active(stack[level][-1]):
							ignore = True
						stack[level].pop()

				if l and not ignore:
					if not stack[level] or stack[level][-1] != "||":
						#Optimize: ( ( ... ) ) -> ( ... )
						stack[level].extend(l)
					elif len(l) == 1 and stack[level][-1] == "||":
						#Optimize: || ( A ) -> A
						stack[level].pop()
						stack[level].extend(l)
					elif len(l) == 2 and l[0] == "||" and stack[level][-1] == "||":
						#Optimize: 	|| ( || ( ... ) ) -> || ( ... )
						stack[level].pop()
						stack[level].extend(l)
					else:
						stack[level].append(l)
			else:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % depstr)
		elif token == "||":
			if need_bracket or is_src_uri:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % depstr)
			need_bracket = True
			stack[level].append(token)
		elif token == "->":
			if not allow_src_uri_file_renames or not is_src_uri or need_simple_token:
				raise portage.exception.InvalidDependString(
					_("SRC_URI arrow not allowed: '%s'") % depstr)
			need_simple_token = True
			stack[level].append(token)	
		else:
			if need_bracket or "(" in token or ")" in token or "|" in token or \
				(need_simple_token and "/" in token):
				if not (need_bracket or "|" in token or (need_simple_token and "/" in token)):
					#We have '(' and/or ')' in token. Make sure it's not a use dep default
					tmp = token.replace("(+)", "").replace("(-)", "")
					if "(" in tmp or ")" in tmp:
						raise portage.exception.InvalidDependString(
							_("malformed syntax: '%s'") % depstr)
				else:
					raise portage.exception.InvalidDependString(
						_("malformed syntax: '%s'") % depstr)

			if token[-1] == "?":
				need_bracket = True
			else:
				need_simple_token = False

			stack[level].append(token)

	if level != 0 or need_bracket or need_simple_token:
		raise portage.exception.InvalidDependString(
			_("malformed syntax: '%s'") % depstr)

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
	newlist = []
	for x in mylist:
		if isinstance(x, list):
			newlist.extend(flatten(x))
		else:
			newlist.append(x)
	return newlist

class _use_dep(object):

	__slots__ = ("__weakref__", "conditional", "missing_enabled", "missing_disabled",
		"disabled", "enabled", "tokens", "required")

	_conditionals_class = portage.cache.mappings.slot_dict_class(
		("disabled", "enabled", "equal", "not_equal"), prefix="")

	_valid_use_re = re.compile(r'^[A-Za-z0-9][A-Za-z0-9+_@-]*$')

	def __init__(self, use):
		enabled_flags = []
		disabled_flags = []
		missing_enabled = []
		missing_disabled = []
		no_default = []

		conditional = self._conditionals_class()
		for k in conditional.allowed_keys:
			conditional[k] = []

		for x in use:
			last_char = x[-1:]
			first_char = x[:1]
			flag = x
			default = ""
			if last_char in ("?", "="):
				flag = flag[:-1]
			if first_char in ("-", "!"):
				flag = flag[1:]

			if flag[-3:] in ("(+)", "(-)"):
				default = flag[-3:]
				flag = flag[:-3]

			if "?" == last_char:
				if "!" == first_char:
					conditional.disabled.append(
						self._validate_flag(x, flag))
				elif first_char in ("-", "=", "?"):
					raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))
				else:
					conditional.enabled.append(
						self._validate_flag(x, flag))

			elif "=" == last_char:
				if "!" == first_char:
					conditional.not_equal.append(
						self._validate_flag(x, flag))
				elif first_char in ("-", "=", "?"):
					raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))
				else:
					conditional.equal.append(
						self._validate_flag(x, flag))

			elif last_char in ("!", "-"):
				raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))

			else:
				if "-" == first_char:
					disabled_flags.append(self._validate_flag(x, flag))
				elif first_char in ("!", "=", "?"):
					raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))
				else:
					enabled_flags.append(self._validate_flag(x, flag))

			if default:
				if default == "(+)":
					if flag in missing_disabled or flag in no_default:
						raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))
					missing_enabled.append(flag)
				else:
					if flag in missing_enabled or flag in no_default:
						raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))
					missing_disabled.append(flag)
			else:
				if flag in missing_enabled or flag in missing_disabled:
					raise InvalidAtom(_("Invalid use dep: '%s'") % (x,))
				no_default.append(flag)

		self.tokens = use
		if not isinstance(self.tokens, tuple):
			self.tokens = tuple(self.tokens)

		self.required = frozenset(chain(
			enabled_flags,
			disabled_flags,
			*conditional.values()
		))

		self.enabled = frozenset(enabled_flags)
		self.disabled = frozenset(disabled_flags)
		self.missing_enabled = frozenset(missing_enabled)
		self.missing_disabled = frozenset(missing_disabled)
		self.conditional = None

		for v in conditional.values():
			if v:
				for k, v in conditional.items():
					conditional[k] = frozenset(v)
				self.conditional = conditional
				break

	def _validate_flag(self, token, flag):
		if self._valid_use_re.match(flag) is None:
			raise InvalidAtom(_("Invalid use dep: '%s'") % (token,))
		return flag

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

	
	def _append_use_default(self, output, flag):
		default = None
		if flag in self.missing_enabled:
			default = "(+)"
		elif flag in self.missing_disabled:
			default = "(-)"

		if not default:
			return output

		if output[-1] in ("=", "?"):
			return output[:-1] + default + output[-1]
		else:
			return output + default

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
		tokens = []

		conditional = self.conditional
		tokens.extend(self._append_use_default(x, x) for x in self.enabled)
		tokens.extend(self._append_use_default("-" + x, x) for x in self.disabled)
		tokens.extend(self._append_use_default(x, x) for x in conditional.enabled if x in use)
		tokens.extend(self._append_use_default("-" + x, x) for x in conditional.disabled if x not in use)

		tokens.extend(self._append_use_default(x, x) for x in conditional.equal if x in use)
		tokens.extend(self._append_use_default("-" + x, x) for x in conditional.equal if x not in use)
		tokens.extend(self._append_use_default("-" + x, x) for x in conditional.not_equal if x in use)
		tokens.extend(self._append_use_default(x, x) for x in conditional.not_equal if x not in use)

		return _use_dep(tokens)

	def violated_conditionals(self, other_use, iuse, parent_use=None):
		"""
		Create a new instance with satisfied use deps removed.
		"""
		tokens = []

		conditional = self.conditional

		for x in self.enabled:
			if x not in other_use:
				if x in iuse:
					tokens.append(self._append_use_default(x, x))
				else:
					if x in self.missing_disabled:
						tokens.append(self._append_use_default(x, x))

		for x in self.disabled:
			if x not in other_use:
				if x not in iuse:
					if x in self.missing_enabled:
						tokens.append(self._append_use_default("-" + x, x))
			else:
				tokens.append(self._append_use_default("-" + x, x))

		if not conditional:
			return _use_dep(tokens)

		if parent_use is None:
			raise InvalidAtom("violated_conditionals needs 'parent_use'" + \
				" parameter for conditional flags.")

		for x in conditional.enabled:
			if x not in parent_use:
				continue

			if x not in other_use:
				if x in iuse:
					tokens.append(self._append_use_default(x + "?", x))
				else:
					if x in self.missing_disabled:
						tokens.append(self._append_use_default(x + "?", x))

		for x in conditional.disabled:
			if x in parent_use:
				continue

			if x not in other_use:
				if x not in iuse:
					if x in self.missing_enabled:
						tokens.append(self._append_use_default("!" + x + "?", x))
			else:
				tokens.append(self._append_use_default("!" + x + "?", x))

		for x in conditional.equal:
			if x not in parent_use:
				continue

			if x not in other_use:
				if x in iuse:
					tokens.append(self._append_use_default(x + "=", x))
				else:
					if x in self.missing_disabled:
						tokens.append(self._append_use_default(x + "=", x))

		for x in conditional.equal:
			if x in parent_use:
				continue

			if x not in other_use:
				if x not in iuse:
					if x in self.missing_enabled:
						tokens.append(self._append_use_default(x + "=", x))
			else:
				tokens.append(self._append_use_default(x + "=", x))

		for x in conditional.not_equal:
			if x in parent_use:
				continue

			if x not in other_use:
				if x in iuse:
					tokens.append(self._append_use_default("!" + x + "=", x))
				else:
					if x in self.missing_disabled:
						tokens.append(self._append_use_default("!" + x + "=", x))

		for x in conditional.not_equal:
			if x not in parent_use:
				continue

			if x not in other_use:
				if x not in iuse:
					if x in self.missing_enabled:
						tokens.append(self._append_use_default("!" + x + "=", x))
			else:
				tokens.append(self._append_use_default("!" + x + "=", x))

		return _use_dep(tokens)

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
		tokens = []

		conditional = self.conditional
		tokens.extend(self._append_use_default(x, x) for x in self.enabled)
		tokens.extend(self._append_use_default("-" + x, x) for x in self.disabled)
		tokens.extend(self._append_use_default(x, x) for x in conditional.enabled if x not in use_mask)
		tokens.extend(self._append_use_default("-" + x, x) for x in conditional.disabled if x not in use_force)

		tokens.extend(self._append_use_default(x, x) for x in conditional.equal if x not in use_mask)
		tokens.extend(self._append_use_default("-" + x, x) for x in conditional.equal if x not in use_force)
		tokens.extend(self._append_use_default("-" + x, x) for x in conditional.not_equal if x not in use_mask)
		tokens.extend(self._append_use_default(x, x) for x in conditional.not_equal if x not in use_force)

		return _use_dep(tokens)

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

	def __new__(cls, s, unevaluated_atom=None, allow_wildcard=False):
		return _atom_base.__new__(cls, s)

	def __init__(self, s, unevaluated_atom=None, allow_wildcard=False):
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
				use_str = None
				extended_syntax = True
			else:
				raise InvalidAtom(self)
		elif m.group('op') is not None:
			base = _atom_re.groupindex['op']
			op = m.group(base + 1)
			cpv = m.group(base + 2)
			cp = m.group(base + 3)
			slot = m.group(_atom_re.groups - 1)
			use_str = m.group(_atom_re.groups)
			if m.group(base + 4) is not None:
				raise InvalidAtom(self)
		elif m.group('star') is not None:
			base = _atom_re.groupindex['star']
			op = '=*'
			cpv = m.group(base + 1)
			cp = m.group(base + 2)
			slot = m.group(_atom_re.groups - 1)
			use_str = m.group(_atom_re.groups)
			if m.group(base + 3) is not None:
				raise InvalidAtom(self)
		elif m.group('simple') is not None:
			op = None
			cpv = cp = m.group(_atom_re.groupindex['simple'] + 1)
			slot = m.group(_atom_re.groups - 1)
			use_str = m.group(_atom_re.groups)
			if m.group(_atom_re.groupindex['simple'] + 2) is not None:
				raise InvalidAtom(self)
		else:
			raise AssertionError(_("required group not found in atom: '%s'") % self)
		self.__dict__['cp'] = cp
		self.__dict__['cpv'] = cpv
		self.__dict__['slot'] = slot
		self.__dict__['operator'] = op
		self.__dict__['extended_syntax'] = extended_syntax

		if use_str is not None:
			use = _use_dep(dep_getusedeps(s))
			without_use = Atom(m.group('without_use'))
		else:
			use = None
			without_use = self

		self.__dict__['use'] = use
		self.__dict__['without_use'] = without_use

		if unevaluated_atom:
			self.__dict__['unevaluated_atom'] = unevaluated_atom
		else:
			self.__dict__['unevaluated_atom'] = self

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
		atom += str(self.use.evaluate_conditionals(use))
		return Atom(atom, unevaluated_atom=self)

	def violated_conditionals(self, other_use, iuse, parent_use=None):
		"""
		Create an atom instance with any USE conditional removed, that is
		satisfied by other_use.
		@param use: The set of enabled USE flags
		@type use: set
		@param use: The set of enabled USE flags to check against
		@type use: set
		@rtype: Atom
		@return: an atom instance with any satisfied USE conditionals removed
		"""
		if not self.use:
			return self
		atom = remove_slot(self)
		if self.slot:
			atom += ":%s" % self.slot
		atom += str(self.use.violated_conditionals(other_use, iuse, parent_use))
		return Atom(atom, unevaluated_atom=self)

	def _eval_qa_conditionals(self, use_mask, use_force):
		if not (self.use and self.use.conditional):
			return self
		atom = remove_slot(self)
		if self.slot:
			atom += ":%s" % self.slot
		atom += str(self.use._eval_qa_conditionals(use_mask, use_force))
		return Atom(atom, unevaluated_atom=self)

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

	def __iter__(self):
		for k in self._normal:
			yield k
		for k in self._extended:
			yield k

	if sys.hexversion >= 0x3000000:
		keys = __iter__

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
	colon = mydep.find(":")
	if colon != -1:
		bracket = mydep.find("[", colon)
		if bracket == -1:
			return mydep[colon+1:]
		else:
			return mydep[colon+1:bracket]
	return None

def remove_slot(mydep):
	"""
	Removes dep components from the right side of an atom:
		* slot
		* use
		* repo
	"""
	colon = mydep.find(":")
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
_slot = r'([\w+][\w+.-]*)'
_slot_re = re.compile('^' + _slot + '$', re.VERBOSE)

_use = r'\[.*\]'
_op = r'([=~]|[><]=?)'

_atom_re = re.compile('^(?P<without_use>(?:' +
	'(?P<op>' + _op + _cpv + ')|' +
	'(?P<star>=' + _cpv + r'\*)|' +
	'(?P<simple>' + _cp + '))(:' + _slot + ')?)(' + _use + ')?$', re.VERBOSE)
	
_extended_cat = r'[\w+*][\w+.*-]*'
_extended_pkg = r'[\w+*][\w+*-]*?'

_atom_wildcard_re = re.compile('(?P<simple>(' + _extended_cat + ')/(' + _extended_pkg + '))(:(?P<slot>' + _slot + '))?$')

def isvalidatom(atom, allow_blockers=False, allow_wildcard=False):
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
			atom = Atom(atom, allow_wildcard=allow_wildcard)
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
		mydep = Atom(mydep)

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
		mydep = mydep[1:]
	if not isinstance(mydep, Atom):
		mydep = Atom(mydep, allow_wildcard=True)

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

	if mydep.use:
		candidate_list = mylist
		mylist = []
		for x in candidate_list:
			use = getattr(x, "use", None)
			if use is not None:
				is_valid_flag = x.iuse.is_valid_flag
				use_config_mismatch = False

				for y in mydep.use.enabled:
					if is_valid_flag(y):
						if y not in use.enabled:
							use_config_mismatch = True
							break	
					else:
						if y not in mydep.use.missing_enabled:
							use_config_mismatch = True
							break

				if use_config_mismatch:
					continue

				for y in mydep.use.disabled:
					if is_valid_flag(y):
						if y in use.enabled:
							use_config_mismatch = True
							break
					else:
						if y not in mydep.use.missing_disabled:
							use_config_mismatch = True
							break

				if use_config_mismatch:
					continue

			mylist.append(x)
	return mylist

def check_required_use(required_use, use, iuse):
	"""
	Checks if the use flags listed in 'use' satisfy all
	constraints specified in 'constraints'.

	@param constraints: REQUIRED_USE string
	@type constraints: String
	@param use: Enabled use flags
	@param use: List
	@param iuse: Referenceable use flags
	@param iuse: List
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

		if not flag or not flag in iuse:
			raise portage.exception.InvalidDependString(
				_("malformed syntax: '%s'") % required_use)

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
	need_bracket = False

	for token in mysplit:
		if token == "(":
			need_bracket = False
			stack.append([])
			level += 1
		elif token == ")":
			if need_bracket:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % required_use)
			if level > 0:
				level -= 1
				l = stack.pop()
				ignore = False
				if stack[level]:
					if stack[level][-1] in ("||", "^^"):
						ignore = True
						op = stack[level].pop()
						stack[level].append(is_satisfied(op, l))
					elif not isinstance(stack[level][-1], bool) and \
						stack[level][-1][-1] == "?":
						if is_active(stack[level][-1][:-1]):
							op = stack[level].pop()
							stack[level].append(is_satisfied(op, l))
						else:
							stack[level].pop()
						ignore = True

				if l and not ignore:
					stack[level].extend(l)
			else:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % required_use)
		elif token in ("||", "^^"):
			if need_bracket:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % required_use)
			need_bracket = True
			stack[level].append(token)
		else:
			if need_bracket or "(" in token or ")" in token or \
				"|" in token or "^" in token:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % required_use)

			if token[-1] == "?":
				need_bracket = True
				stack[level].append(token)
			else:
				stack[level].append(is_active(token))

	if level != 0 or need_bracket:
		raise portage.exception.InvalidDependString(
			_("malformed syntax: '%s'") % required_use)

	return (False not in stack[0])

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
			raise portage.exception.InvalidDependString(
				_("malformed syntax: '%s'") % mystr)

		return flag

	for token in mysplit:
		if token == "(":
			need_bracket = False
			stack.append([])
			level += 1
		elif token == ")":
			if need_bracket:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
			if level > 0:
				level -= 1
				l = stack.pop()

				if l:
					if not stack[level] or (stack[level][-1] != "||" and not stack[level][-1][-1] == "?"):
						#Optimize: ( ( ... ) ) -> ( ... )
						stack[level].extend(l)
					elif len(l) == 1 and stack[level][-1] == "||":
						#Optimize: || ( A ) -> A
						stack[level].pop()
						stack[level].extend(l)
					elif len(l) == 2 and (l[0] == "||" or l[0][-1] == "?") and stack[level][-1] in (l[0], "||"):
						#Optimize: 	|| ( || ( ... ) ) -> || ( ... )
						#			foo? ( foo? ( ... ) ) -> foo? ( ... )
						#			|| ( foo? ( ... ) ) -> foo? ( ... )
						stack[level].pop()
						stack[level].extend(l)
						if l[0][-1] == "?":
							affecting_use.add(flag(l[0]))
					else:
						if stack[level] and stack[level][-1][-1] == "?":
							affecting_use.add(flag(stack[level][-1]))
						stack[level].append(l)
				else:
					if stack[level] and (stack[level][-1] == "||" or stack[level][-1][-1] == "?"):
						stack[level].pop()
			else:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
		elif token == "||":
			if need_bracket:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
			need_bracket = True
			stack[level].append(token)
		else:
			if need_bracket or "(" in token or ")" in token or "|" in token:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % mystr)

			if token[-1] == "?":
				need_bracket = True
				stack[level].append(token)
			elif token == atom:
				stack[level].append(token)

	if level != 0 or need_bracket:
		raise portage.exception.InvalidDependString(
			_("malformed syntax: '%s'") % mystr)

	return affecting_use
