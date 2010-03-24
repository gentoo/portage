# deps.py -- Portage dependency resolution functions
# Copyright 2003-2004 Gentoo Foundation
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
	return [x for x in myarr if x]

_paren_whitespace_re = re.compile(r'\S(\(|\))|(\(|\))\S')

def paren_reduce(mystr,tokenize=1):
	"""
	Take a string and convert all paren enclosed entities into sublists, optionally
	futher splitting the list elements by spaces.

	Example usage:
		>>> paren_reduce('foobar foo ( bar baz )',1)
		['foobar', 'foo', ['bar', 'baz']]
		>>> paren_reduce('foobar foo ( bar baz )',0)
		['foobar foo ', [' bar baz ']]

	@param mystr: The string to reduce
	@type mystr: String
	@param tokenize: Split on spaces to produces further list breakdown
	@type tokenize: Integer
	@rtype: Array
	@return: The reduced string in an array
	"""
	global _dep_check_strict, _paren_whitespace_re
	if _dep_check_strict:
		m = _paren_whitespace_re.search(mystr)
		if m is not None:
			raise portage.exception.InvalidDependString(
				_("missing space by parenthesis: '%s'") % m.group(0))
	mylist = []
	while mystr:
		left_paren = mystr.find("(")
		has_left_paren = left_paren != -1
		right_paren = mystr.find(")")
		has_right_paren = right_paren != -1
		if not has_left_paren and not has_right_paren:
			freesec = mystr
			subsec = None
			tail = ""
		elif mystr[0] == ")":
			return [mylist,mystr[1:]]
		elif has_left_paren and not has_right_paren:
			raise portage.exception.InvalidDependString(
				_("missing right parenthesis: '%s'") % mystr)
		elif has_left_paren and left_paren < right_paren:
			freesec,subsec = mystr.split("(",1)
			sublist = paren_reduce(subsec, tokenize=tokenize)
			if len(sublist) != 2:
				raise portage.exception.InvalidDependString(
					_("malformed syntax: '%s'") % mystr)
			subsec, tail = sublist
		else:
			subsec,tail = mystr.split(")",1)
			if tokenize:
				subsec = strip_empty(subsec.split(" "))
				return [mylist+subsec,tail]
			return mylist+[subsec],tail
		if not isinstance(tail, basestring):
			raise portage.exception.InvalidDependString(
				_("malformed syntax: '%s'") % mystr)
		mystr = tail
		if freesec:
			if tokenize:
				mylist = mylist + strip_empty(freesec.split(" "))
			else:
				mylist = mylist + [freesec]
		if subsec is not None:
			mylist = mylist + [subsec]
	return mylist

class paren_normalize(list):
	"""Take a dependency structure as returned by paren_reduce or use_reduce
	and generate an equivalent structure that has no redundant lists."""
	def __init__(self, src):
		list.__init__(self)
		self._zap_parens(src, self)

	def _zap_parens(self, src, dest, disjunction=False):
		if not src:
			return dest
		i = iter(src)
		for x in i:
			if isinstance(x, basestring):
				if x == '||':
					x = self._zap_parens(next(i), [], disjunction=True)
					if len(x) == 1:
						dest.append(x[0])
					else:
						dest.append("||")
						dest.append(x)
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

# This is just for use by emerge so that it can enable a backward compatibility
# mode in order to gracefully deal with installed packages that have invalid
# atoms or dep syntax.  For backward compatibility with api consumers, strict
# behavior will be explicitly enabled as necessary.
_dep_check_strict = False

def use_reduce(deparray, uselist=[], masklist=[], matchall=0, excludeall=[]):
	"""
	Takes a paren_reduce'd array and reduces the use? conditionals out
	leaving an array with subarrays

	@param deparray: paren_reduce'd list of deps
	@type deparray: List
	@param uselist: List of use flags
	@type uselist: List
	@param masklist: List of masked flags
	@type masklist: List
	@param matchall: Resolve all conditional deps unconditionally.  Used by repoman
	@type matchall: Integer
	@rtype: List
	@return: The use reduced depend array
	"""
	# Quick validity checks
	for x, y in enumerate(deparray):
		if y == '||':
			if len(deparray) - 1 == x or not isinstance(deparray[x+1], list):
				raise portage.exception.InvalidDependString(_('%(dep)s missing atom list in "%(deparray)s"') % {"dep": deparray[x], "deparray": paren_enclose(deparray)})
	if deparray and deparray[-1] and deparray[-1][-1] == "?":
		raise portage.exception.InvalidDependString(_('Conditional without target in "%s"') % paren_enclose(deparray))

	global _dep_check_strict

	mydeparray = deparray[:]
	rlist = []
	while mydeparray:
		head = mydeparray.pop(0)

		if not isinstance(head, basestring):
			additions = use_reduce(head, uselist, masklist, matchall, excludeall)
			if additions:
				rlist.append(additions)
			elif rlist and rlist[-1] == "||":
			#XXX: Currently some DEPEND strings have || lists without default atoms.
			#	raise portage.exception.InvalidDependString("No default atom(s) in \""+paren_enclose(deparray)+"\"")
				rlist.append([])

		else:
			if head[-1:] == "?": # Use reduce next group on fail.
				# Pull any other use conditions and the following atom or list into a separate array
				newdeparray = [head]
				while isinstance(newdeparray[-1], basestring) and \
					newdeparray[-1][-1:] == "?":
					if mydeparray:
						newdeparray.append(mydeparray.pop(0))
					else:
						raise ValueError(_("Conditional with no target."))

				# Deprecation checks
				warned = 0
				if len(newdeparray[-1]) == 0:
					sys.stderr.write(_("Note: Empty target in string. (Deprecated)\n"))
					warned = 1
				if len(newdeparray) != 2:
					sys.stderr.write(_("Note: Nested use flags without parenthesis (Deprecated)\n"))
					warned = 1
				if warned:
					sys.stderr.write("  --> "+" ".join(map(str,[head]+newdeparray))+"\n")

				# Check that each flag matches
				ismatch = True
				missing_flag = False
				for head in newdeparray[:-1]:
					head = head[:-1]
					if not head:
						missing_flag = True
						break
					if head.startswith("!"):
						head_key = head[1:]
						if not head_key:
							missing_flag = True
							break
						if not matchall and head_key in uselist or \
							head_key in excludeall:
							ismatch = False
							break
					elif head not in masklist:
						if not matchall and head not in uselist:
							ismatch = False
							break
					else:
						ismatch = False
				if missing_flag:
					raise portage.exception.InvalidDependString(
						_('Conditional without flag: "') + \
						paren_enclose([head+"?", newdeparray[-1]])+"\"")

				# If they all match, process the target
				if ismatch:
					target = newdeparray[-1]
					if isinstance(target, list):
						additions = use_reduce(target, uselist, masklist, matchall, excludeall)
						if additions:
							rlist.append(additions)
					elif not _dep_check_strict:
						# The old deprecated behavior.
						rlist.append(target)
					else:
						raise portage.exception.InvalidDependString(
							_("Conditional without parenthesis: '%s?'") % head)

			else:
				rlist += [head]

	return rlist

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
		elif deplist[x] == "||" or deplist[x] == "&&":
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

	__slots__ = ("__weakref__", "conditional",
		"disabled", "enabled", "tokens", "required")

	_conditionals_class = portage.cache.mappings.slot_dict_class(
		("disabled", "enabled", "equal", "not_equal"), prefix="")

	_valid_use_re = re.compile(r'^[^-?!=][^?!=]*$')

	def __init__(self, use):
		enabled_flags = []
		disabled_flags = []
		conditional = self._conditionals_class()
		for k in conditional.allowed_keys:
			conditional[k] = []

		for x in use:
			last_char = x[-1:]
			first_char = x[:1]

			if "?" == last_char:
				if "!" == first_char:
					conditional.disabled.append(
						self._validate_flag(x, x[1:-1]))
				else:
					conditional.enabled.append(
						self._validate_flag(x, x[:-1]))

			elif "=" == last_char:
				if "!" == first_char:
					conditional.not_equal.append(
						self._validate_flag(x, x[1:-1]))
				else:
					conditional.equal.append(
						self._validate_flag(x, x[:-1]))

			else:
				if "-" == first_char:
					disabled_flags.append(self._validate_flag(x, x[1:]))
				else:
					enabled_flags.append(self._validate_flag(x, x))

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
		tokens.extend(self.enabled)
		tokens.extend("-" + x for x in self.disabled)
		tokens.extend(x for x in conditional.enabled if x in use)
		tokens.extend("-" + x for x in conditional.disabled if x not in use)

		tokens.extend(x for x in conditional.equal if x in use)
		tokens.extend("-" + x for x in conditional.equal if x not in use)
		tokens.extend("-" + x for x in conditional.not_equal if x in use)
		tokens.extend(x for x in conditional.not_equal if x not in use)

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
		tokens.extend(self.enabled)
		tokens.extend("-" + x for x in self.disabled)
		tokens.extend(x for x in conditional.enabled if x not in use_mask)
		tokens.extend("-" + x for x in conditional.disabled if x not in use_force)

		tokens.extend(x for x in conditional.equal if x not in use_mask)
		tokens.extend("-" + x for x in conditional.equal if x not in use_force)
		tokens.extend("-" + x for x in conditional.not_equal if x not in use_mask)
		tokens.extend(x for x in conditional.not_equal if x not in use_force)

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

	def __init__(self, s):
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
		if m is None:
			raise InvalidAtom(self)

		if m.group('op') is not None:
			base = _atom_re.groupindex['op']
			op = m.group(base + 1)
			cpv = m.group(base + 2)
			cp = m.group(base + 3)
			if m.group(base + 4) is not None:
				raise InvalidAtom(self)
		elif m.group('star') is not None:
			base = _atom_re.groupindex['star']
			op = '=*'
			cpv = m.group(base + 1)
			cp = m.group(base + 2)
			if m.group(base + 3) is not None:
				raise InvalidAtom(self)
		elif m.group('simple') is not None:
			op = None
			cpv = cp = m.group(_atom_re.groupindex['simple'] + 1)
			if m.group(_atom_re.groupindex['simple'] + 2) is not None:
				raise InvalidAtom(self)
		else:
			raise AssertionError(_("required group not found in atom: '%s'") % self)
		self.__dict__['cp'] = cp
		self.__dict__['cpv'] = cpv
		self.__dict__['slot'] = m.group(_atom_re.groups - 1)
		self.__dict__['operator'] = op

		use_str = m.group(_atom_re.groups)
		if use_str is not None:
			use = _use_dep(dep_getusedeps(s))
			without_use = Atom(m.group('without_use'))
		else:
			use = None
			without_use = self

		self.__dict__['use'] = use
		self.__dict__['without_use'] = without_use

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
		return Atom(atom)

	def __copy__(self):
		"""Immutable, so returns self."""
		return self

	def __deepcopy__(self, memo=None):
		"""Immutable, so returns self."""
		memo[id(self)] = self
		return self

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
	if isinstance(mydep, Atom):
		return mydep.operator
	try:
		return Atom(mydep).operator
	except InvalidAtom:
		pass

	# Fall back to legacy code for backward compatibility.
	warnings.warn(_("%s is deprecated, use %s instead") % \
		('portage.dep.get_operator()', 'portage.dep.Atom.operator'),
		DeprecationWarning)
	operator = None
	if mydep:
		mydep = remove_slot(mydep)
	if not mydep:
		return None
	if mydep[0] == "~":
		operator = "~"
	elif mydep[0] == "=":
		if mydep[-1] == "*":
			operator = "=*"
		else:
			operator = "="
	elif mydep[0] in "><":
		if len(mydep) > 1 and mydep[1] == "=":
			operator = mydep[0:2]
		else:
			operator = mydep[0]
	else:
		operator = None

	return operator

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
	if isinstance(mydep, Atom):
		return mydep.cpv
	try:
		return Atom(mydep).cpv
	except InvalidAtom:
		pass

	# Fall back to legacy code for backward compatibility.
	warnings.warn(_("%s is deprecated, use %s instead") % \
		('portage.dep.dep_getcpv()', 'portage.dep.Atom.cpv'),
		DeprecationWarning, stacklevel=2)
	mydep_orig = mydep
	if mydep:
		mydep = remove_slot(mydep)
	if mydep and mydep[0] == "*":
		mydep = mydep[1:]
	if mydep and mydep[-1] == "*":
		mydep = mydep[:-1]
	if mydep and mydep[0] == "!":
		if mydep[1:2] == "!":
			mydep = mydep[2:]
		else:
			mydep = mydep[1:]
	if mydep[:2] in [">=", "<="]:
		mydep = mydep[2:]
	elif mydep[:1] in "=<>~":
		mydep = mydep[1:]
	return mydep

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

def isvalidatom(atom, allow_blockers=False):
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
			atom = Atom(atom)
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
	if isinstance(mydep, Atom):
		return mydep.cp
	try:
		return Atom(mydep).cp
	except InvalidAtom:
		try:
			atom = Atom('=' + mydep)
		except InvalidAtom:
			pass
		else:
			warnings.warn(_("invalid input to %s: '%s', use %s instead") % \
				('portage.dep.dep_getkey()', mydep, 'portage.cpv_getkey()'),
				DeprecationWarning, stacklevel=2)
			return atom.cp

	# Fall back to legacy code for backward compatibility.
	warnings.warn(_("%s is deprecated, use %s instead") % \
		('portage.dep.dep_getkey()', 'portage.dep.Atom.cp'),
		DeprecationWarning, stacklevel=2)
	mydep = dep_getcpv(mydep)
	if mydep and isspecific(mydep):
		mysplit = catpkgsplit(mydep)
		if not mysplit:
			return mydep
		return mysplit[0] + "/" + mysplit[1]
	else:
		return mydep

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
	"""
	operator_values = {'=':6, '~':5, '=*':4,
		'>':2, '<':2, '>=':2, '<=':2, None:1}
	maxvalue = 0
	bestm  = None
	for x in match_to_list(mypkg, mylist):
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
		mydep = Atom(mydep)

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
			if cp != mycpv:
				continue
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

	if slot is not None:
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
				regex = x.iuse.regex
				missing_iuse = False
				for y in mydep.use.required:
					if regex.match(y) is None:
						missing_iuse = True
						break
				if missing_iuse:
					continue
				if mydep.use.enabled.difference(use.enabled):
					continue
				if mydep.use.disabled.intersection(use.enabled):
					continue
			mylist.append(x)

	return mylist
