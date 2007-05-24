# deps.py -- Portage dependency resolution functions
# Copyright 2003-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


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

import re, sys, types
import portage.exception
from portage.exception import InvalidData, InvalidAtom
from portage.versions import catpkgsplit, catsplit, pkgcmp, pkgsplit, ververify

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
		raise portage.exception.PortageException("Invalid data '%s, %s', parameter was not a CPV" % (cpv1, cpv2))
	
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

	for x in range(len(myarr)-1, -1, -1):
		if not myarr[x]:
			del myarr[x]
	return myarr

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
	mylist = []
	while mystr:
		if ("(" not in mystr) and (")" not in mystr):
			freesec = mystr
			subsec = None
			tail = ""
		elif mystr[0] == ")":
			return [mylist,mystr[1:]]
		elif ("(" in mystr) and (mystr.index("(") < mystr.index(")")):
			freesec,subsec = mystr.split("(",1)
			subsec,tail = paren_reduce(subsec,tokenize)
		else:
			subsec,tail = mystr.split(")",1)
			if tokenize:
				subsec = strip_empty(subsec.split(" "))
				return [mylist+subsec,tail]
			return mylist+[subsec],tail
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
		self._zap_parens(src, self)

	def _zap_parens(self, src, dest, disjunction=False):
		if not src:
			return dest
		i = iter(src)
		for x in i:
			if isinstance(x, basestring):
				if x == '||':
					x = i.next()
					if len(x) == 1:
						if isinstance(x[0], basestring):
							dest.append(x[0])
						else:
							self._zap_parens(x, dest, disjunction=disjunction)
					else:
						dest.append("||")
						dest.append(self._zap_parens(x, [], disjunction=True))
				elif x.endswith("?"):
					dest.append(x)
					dest.append(self._zap_parens(i.next(), []))
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
	for x in range(len(deparray)):
		if deparray[x] in ["||","&&"]:
			if len(deparray) - 1 == x or not isinstance(deparray[x+1], list):
				raise portage.exception.InvalidDependString(deparray[x]+" missing atom list in \""+paren_enclose(deparray)+"\"")
	if deparray and deparray[-1] and deparray[-1][-1] == "?":
		raise portage.exception.InvalidDependString("Conditional without target in \""+paren_enclose(deparray)+"\"")

	global _dep_check_strict

	mydeparray = deparray[:]
	rlist = []
	while mydeparray:
		head = mydeparray.pop(0)

		if type(head) == types.ListType:
			additions = use_reduce(head, uselist, masklist, matchall, excludeall)
			if additions:
				rlist.append(additions)
			elif rlist and rlist[-1] == "||":
			#XXX: Currently some DEPEND strings have || lists without default atoms.
			#	raise portage.exception.InvalidDependString("No default atom(s) in \""+paren_enclose(deparray)+"\"")
				rlist.append([])

		else:
			if head[-1] == "?": # Use reduce next group on fail.
				# Pull any other use conditions and the following atom or list into a separate array
				newdeparray = [head]
				while isinstance(newdeparray[-1], str) and newdeparray[-1][-1] == "?":
					if mydeparray:
						newdeparray.append(mydeparray.pop(0))
					else:
						raise ValueError, "Conditional with no target."

				# Deprecation checks
				warned = 0
				if len(newdeparray[-1]) == 0:
					sys.stderr.write("Note: Empty target in string. (Deprecated)\n")
					warned = 1
				if len(newdeparray) != 2:
					sys.stderr.write("Note: Nested use flags without parenthesis (Deprecated)\n")
					warned = 1
				if warned:
					sys.stderr.write("  --> "+" ".join(map(str,[head]+newdeparray))+"\n")

				# Check that each flag matches
				ismatch = True
				for head in newdeparray[:-1]:
					head = head[:-1]
					if head[0] == "!":
						head_key = head[1:]
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
							"Conditional without parenthesis: '%s?'" % head)

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

_dep_getcpv_cache = {}

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
	global _dep_getcpv_cache
	retval = _dep_getcpv_cache.get(mydep, None)
	if retval is not None:
		return retval
	mydep_orig = mydep
	if mydep and mydep[0] == "*":
		mydep = mydep[1:]
	if mydep and mydep[-1] == "*":
		mydep = mydep[:-1]
	if mydep and mydep[0] == "!":
		mydep = mydep[1:]
	if mydep[:2] in [">=", "<="]:
		mydep = mydep[2:]
	elif mydep[:1] in "=<>~":
		mydep = mydep[1:]
	colon = mydep.rfind(":")
	if colon != -1:
		mydep = mydep[:colon]
	_dep_getcpv_cache[mydep_orig] = mydep
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
	colon = mydep.rfind(":")
	if colon != -1:
		return mydep[colon+1:]
	return None

def dep_getusedeps( depend ):
	"""
	Pull a listing of USE Dependencies out of a dep atom.
	
	Example usage:
		>>> dep_getusedeps('app-misc/test:3[foo][-bar]')
		['foo','-bar']
	
	@param depend: The depstring to process
	@type depend: String
	@rtype: List
	@return: List of use flags ( or [] if no flags exist )
	"""
	use_list = []
	open_bracket = depend.find('[')
	# -1 = failure (think c++ string::npos)
	while( open_bracket != -1 ):
		close_bracket = depend.find(']', open_bracket )
		if close_bracket == -1:
			raise InvalidAtom("USE Dependency with no closing bracket: %s" % depend )
		use = depend[open_bracket + 1: close_bracket]
		# foo[1:1] may return '' instead of None, we don't want '' in the result
		if len(use):
			use_list.append(use)
		else:
			raise InvalidAtom("USE Dependency with no use flag ([]): %s" % depend )
		# Find next use flag
		open_bracket = depend.find( '[', open_bracket+1 )
	return use_list

_invalid_atom_chars_regexp = re.compile("[()|?]")

def isvalidatom(atom, allow_blockers=False):
	"""
	Check to see if a depend atom is valid

	Example usage:
		>>> isvalidatom('media-libs/test-3.0')
		0
		>>> isvalidatom('>=media-libs/test-3.0')
		1

	@param atom: The depend atom to check against
	@type atom: String
	@rtype: Integer
	@return: One of the following:
		1) 0 if the atom is invalid
		2) 1 if the atom is valid
	"""
	global _invalid_atom_chars_regexp
	if _invalid_atom_chars_regexp.search(atom):
		return 0
	if allow_blockers and atom.startswith("!"):
		atom = atom[1:]
	try:
		mycpv_cps = catpkgsplit(dep_getcpv(atom))
	except InvalidData:
		return 0
	operator = get_operator(atom)
	if operator:
		if operator[0] in "<>" and atom[-1] == "*":
			return 0
		if mycpv_cps and mycpv_cps[0] != "null":
			# >=cat/pkg-1.0
			return 1
		else:
			# >=cat/pkg or >=pkg-1.0 (no category)
			return 0
	if mycpv_cps:
		# cat/pkg-1.0
		return 0

	if (len(atom.split('/')) == 2):
		# cat/pkg
		return 1
	else:
		return 0

def isjustname(mypkg):
	"""
	Checks to see if the depstring is only the package name (no version parts)

	Example usage:
		>>> isjustname('media-libs/test-3.0')
		0
		>>> isjustname('test')
		1
		>>> isjustname('media-libs/test')
		1

	@param mypkg: The package atom to check
	@param mypkg: String
	@rtype: Integer
	@return: One of the following:
		1) 0 if the package string is not just the package name
		2) 1 if it is
	"""
	myparts = mypkg.split('-')
	for x in myparts:
		if ververify(x):
			return 0
	return 1

iscache = {}

def isspecific(mypkg):
	"""
	Checks to see if a package is in category/package-version or package-version format,
	possibly returning a cached result.

	Example usage:
		>>> isspecific('media-libs/test')
		0
		>>> isspecific('media-libs/test-3.0')
		1

	@param mypkg: The package depstring to check against
	@type mypkg: String
	@rtype: Integer
	@return: One of the following:
		1) 0 if the package string is not specific
		2) 1 if it is
	"""
	try:
		return iscache[mypkg]
	except KeyError:
		pass
	mysplit = mypkg.split("/")
	if not isjustname(mysplit[-1]):
			iscache[mypkg] = 1
			return 1
	iscache[mypkg] = 0
	return 0

def dep_getkey(mydep):
	"""
	Return the category/package-name of a depstring.

	Example usage:
		>>> dep_getkey('media-libs/test-3.0')
		'media-libs/test'

	@param mydep: The depstring to retrieve the category/package-name of
	@type mydep: String
	@rtype: String
	@return: The package category/package-version
	"""
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
	matches = []
	for x in mylist:
		if match_from_list(x, [mypkg]):
			if x not in matches:
				matches.append(x)
	return matches

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
			continue
		op_val = operator_values[get_operator(x)]
		if op_val > maxvalue:
			maxvalue = op_val
			bestm  = x
	return bestm

_match_from_list_cache = {}

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

	global _match_from_list_cache
	cache_key = (mydep, tuple(candidate_list))
	mylist = _match_from_list_cache.get(cache_key, None)
	if mylist is not None:
		return mylist[:]

	from portage.util import writemsg
	if mydep[0] == "!":
		mydep = mydep[1:]

	mycpv     = dep_getcpv(mydep)
	mycpv_cps = catpkgsplit(mycpv) # Can be None if not specific
	slot      = None

	if not mycpv_cps:
		cat, pkg = catsplit(mycpv)
		ver      = None
		rev      = None
		slot = dep_getslot(mydep)
	else:
		cat, pkg, ver, rev = mycpv_cps
		if mydep == mycpv:
			raise KeyError("Specific key requires an operator" + \
				" (%s) (try adding an '=')" % (mydep))

	if ver and rev:
		operator = get_operator(mydep)
		if not operator:
			writemsg("!!! Invalid atom: %s\n" % mydep, noiselevel=-1)
			return []
	else:
		operator = None

	mylist = []

	if operator is None:
		for x in candidate_list:
			xs = pkgsplit(x)
			if xs is None:
				xcpv = dep_getcpv(x)
				if slot is not None:
					xslot = dep_getslot(x)
					if xslot is not None and xslot != slot:
						"""  This function isn't given enough information to
						reject atoms based on slot unless *both* compared atoms
						specify slots."""
						continue
				if xcpv != mycpv:
					continue
			elif xs[0] != mycpv:
				continue
			mylist.append(x)

	elif operator == "=": # Exact match
		mylist = [cpv for cpv in candidate_list if cpvequal(cpv, mycpv)]

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
			xs = catpkgsplit(x)
			myver = xs[2].lstrip("0")
			if not myver or not myver[0].isdigit():
				myver = "0"+myver
			xcpv = xs[0]+"/"+xs[1]+"-"+myver
			if xcpv.startswith(mycpv):
				mylist.append(x)

	elif operator == "~": # version, any revision, match
		for x in candidate_list:
			xs = catpkgsplit(x)
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
			try:
				result = pkgcmp(pkgsplit(x), mysplit)
			except ValueError: # pkgcmp may return ValueError during int() conversion
				writemsg("\nInvalid package name: %s\n" % x, noiselevel=-1)
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
				raise KeyError("Unknown operator: %s" % mydep)
	else:
		raise KeyError("Unknown operator: %s" % mydep)

	_match_from_list_cache[cache_key] = mylist
	return mylist
