# versions.py -- core Portage functionality
# Copyright 1998-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = [
	'best', 'catpkgsplit', 'catsplit',
	'cpv_getkey', 'cpv_getversion', 'cpv_sort_key', 'pkgcmp',  'pkgsplit',
	'ververify', 'vercmp'
]

import re
import warnings

import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util:cmp_sort_key'
)
from portage.localization import _

# \w is [a-zA-Z0-9_]

# 2.1.1 A category name may contain any of the characters [A-Za-z0-9+_.-].
# It must not begin with a hyphen or a dot.
_cat = r'[\w+][\w+.-]*'

# 2.1.2 A package name may contain any of the characters [A-Za-z0-9+_-].
# It must not begin with a hyphen,
# and must not end in a hyphen followed by one or more digits.
_pkg = r'[\w+][\w+-]*?'

_v = r'(cvs\.)?(\d+)((\.\d+)*)([a-z]?)((_(pre|p|beta|alpha|rc)\d*)*)'
_rev = r'\d+'
_vr = _v + '(-r(' + _rev + '))?'

_cp = '(' + _cat + '/' + _pkg + '(-' + _vr + ')?)'
_cpv = '(' + _cp + '-' + _vr + ')'
_pv = '(?P<pn>' + _pkg + '(?P<pn_inval>-' + _vr + ')?)' + '-(?P<ver>' + _v + ')(-r(?P<rev>' + _rev + '))?'

ver_regexp = re.compile("^" + _vr + "$")
suffix_regexp = re.compile("^(alpha|beta|rc|pre|p)(\\d*)$")
suffix_value = {"pre": -2, "p": 0, "alpha": -4, "beta": -3, "rc": -1}
endversion_keys = ["pre", "p", "alpha", "beta", "rc"]

def ververify(myver, silent=1):
	if ver_regexp.match(myver):
		return 1
	else:
		if not silent:
			print(_("!!! syntax error in version: %s") % myver)
		return 0

vercmp_cache = {}
def vercmp(ver1, ver2, silent=1):
	"""
	Compare two versions
	Example usage:
		>>> from portage.versions import vercmp
		>>> vercmp('1.0-r1','1.2-r3')
		negative number
		>>> vercmp('1.3','1.2-r3')
		positive number
		>>> vercmp('1.0_p3','1.0_p3')
		0
	
	@param pkg1: version to compare with (see ver_regexp in portage.versions.py)
	@type pkg1: string (example: "2.1.2-r3")
	@param pkg2: version to compare againts (see ver_regexp in portage.versions.py)
	@type pkg2: string (example: "2.1.2_rc5")
	@rtype: None or float
	@return:
	1. positive if ver1 is greater than ver2
	2. negative if ver1 is less than ver2 
	3. 0 if ver1 equals ver2
	4. None if ver1 or ver2 are invalid (see ver_regexp in portage.versions.py)
	"""

	if ver1 == ver2:
		return 0
	mykey=ver1+":"+ver2
	try:
		return vercmp_cache[mykey]
	except KeyError:
		pass
	match1 = ver_regexp.match(ver1)
	match2 = ver_regexp.match(ver2)
	
	# checking that the versions are valid
	if not match1 or not match1.groups():
		if not silent:
			print(_("!!! syntax error in version: %s") % ver1)
		return None
	if not match2 or not match2.groups():
		if not silent:
			print(_("!!! syntax error in version: %s") % ver2)
		return None

	# shortcut for cvs ebuilds (new style)
	if match1.group(1) and not match2.group(1):
		vercmp_cache[mykey] = 1
		return 1
	elif match2.group(1) and not match1.group(1):
		vercmp_cache[mykey] = -1
		return -1
	
	# building lists of the version parts before the suffix
	# first part is simple
	list1 = [int(match1.group(2))]
	list2 = [int(match2.group(2))]

	# this part would greatly benefit from a fixed-length version pattern
	if match1.group(3) or match2.group(3):
		vlist1 = match1.group(3)[1:].split(".")
		vlist2 = match2.group(3)[1:].split(".")

		for i in range(0, max(len(vlist1), len(vlist2))):
			# Implcit .0 is given a value of -1, so that 1.0.0 > 1.0, since it
			# would be ambiguous if two versions that aren't literally equal
			# are given the same value (in sorting, for example).
			if len(vlist1) <= i or len(vlist1[i]) == 0:
				list1.append(-1)
				list2.append(int(vlist2[i]))
			elif len(vlist2) <= i or len(vlist2[i]) == 0:
				list1.append(int(vlist1[i]))
				list2.append(-1)
			# Let's make life easy and use integers unless we're forced to use floats
			elif (vlist1[i][0] != "0" and vlist2[i][0] != "0"):
				list1.append(int(vlist1[i]))
				list2.append(int(vlist2[i]))
			# now we have to use floats so 1.02 compares correctly against 1.1
			else:
				# list1.append(float("0."+vlist1[i]))
				# list2.append(float("0."+vlist2[i]))
				# Since python floats have limited range, we multiply both
				# floating point representations by a constant so that they are
				# transformed into whole numbers. This allows the practically
				# infinite range of a python int to be exploited. The
				# multiplication is done by padding both literal strings with
				# zeros as necessary to ensure equal length.
				max_len = max(len(vlist1[i]), len(vlist2[i]))
				list1.append(int(vlist1[i].ljust(max_len, "0")))
				list2.append(int(vlist2[i].ljust(max_len, "0")))

	# and now the final letter
	# NOTE: Behavior changed in r2309 (between portage-2.0.x and portage-2.1).
	# The new behavior is 12.2.5 > 12.2b which, depending on how you look at,
	# may seem counter-intuitive. However, if you really think about it, it
	# seems like it's probably safe to assume that this is the behavior that
	# is intended by anyone who would use versions such as these.
	if len(match1.group(5)):
		list1.append(ord(match1.group(5)))
	if len(match2.group(5)):
		list2.append(ord(match2.group(5)))

	for i in range(0, max(len(list1), len(list2))):
		if len(list1) <= i:
			vercmp_cache[mykey] = -1
			return -1
		elif len(list2) <= i:
			vercmp_cache[mykey] = 1
			return 1
		elif list1[i] != list2[i]:
			a = list1[i]
			b = list2[i]
			rval = (a > b) - (a < b)
			vercmp_cache[mykey] = rval
			return rval

	# main version is equal, so now compare the _suffix part
	list1 = match1.group(6).split("_")[1:]
	list2 = match2.group(6).split("_")[1:]
	
	for i in range(0, max(len(list1), len(list2))):
		# Implicit _p0 is given a value of -1, so that 1 < 1_p0
		if len(list1) <= i:
			s1 = ("p","-1")
		else:
			s1 = suffix_regexp.match(list1[i]).groups()
		if len(list2) <= i:
			s2 = ("p","-1")
		else:
			s2 = suffix_regexp.match(list2[i]).groups()
		if s1[0] != s2[0]:
			a = suffix_value[s1[0]]
			b = suffix_value[s2[0]]
			rval = (a > b) - (a < b)
			vercmp_cache[mykey] = rval
			return rval
		if s1[1] != s2[1]:
			# it's possible that the s(1|2)[1] == ''
			# in such a case, fudge it.
			try:
				r1 = int(s1[1])
			except ValueError:
				r1 = 0
			try:
				r2 = int(s2[1])
			except ValueError:
				r2 = 0
			rval = (r1 > r2) - (r1 < r2)
			if rval:
				vercmp_cache[mykey] = rval
				return rval

	# the suffix part is equal to, so finally check the revision
	if match1.group(10):
		r1 = int(match1.group(10))
	else:
		r1 = 0
	if match2.group(10):
		r2 = int(match2.group(10))
	else:
		r2 = 0
	rval = (r1 > r2) - (r1 < r2)
	vercmp_cache[mykey] = rval
	return rval
	
def pkgcmp(pkg1, pkg2):
	"""
	Compare 2 package versions created in pkgsplit format.

	Example usage:
		>>> from portage.versions import *
		>>> pkgcmp(pkgsplit('test-1.0-r1'),pkgsplit('test-1.2-r3'))
		-1
		>>> pkgcmp(pkgsplit('test-1.3'),pkgsplit('test-1.2-r3'))
		1

	@param pkg1: package to compare with
	@type pkg1: list (example: ['test', '1.0', 'r1'])
	@param pkg2: package to compare againts
	@type pkg2: list (example: ['test', '1.0', 'r1'])
	@rtype: None or integer
	@return: 
		1. None if package names are not the same
		2. 1 if pkg1 is greater than pkg2
		3. -1 if pkg1 is less than pkg2 
		4. 0 if pkg1 equals pkg2
	"""
	if pkg1[0] != pkg2[0]:
		return None
	return vercmp("-".join(pkg1[1:]), "-".join(pkg2[1:]))

_pv_re = re.compile('^' + _pv + '$', re.VERBOSE)

def _pkgsplit(mypkg):
	"""
	@param mypkg: pv
	@return:
	1. None if input is invalid.
	2. (pn, ver, rev) if input is pv
	"""
	m = _pv_re.match(mypkg)
	if m is None:
		return None

	if m.group('pn_inval') is not None:
		# package name appears to have a version-like suffix
		return None

	rev = m.group('rev')
	if rev is None:
		rev = '0'
	rev = 'r' + rev

	return  (m.group('pn'), m.group('ver'), rev) 

_cat_re = re.compile('^%s$' % _cat)
_missing_cat = 'null'
catcache={}
def catpkgsplit(mydata,silent=1):
	"""
	Takes a Category/Package-Version-Rev and returns a list of each.
	
	@param mydata: Data to split
	@type mydata: string 
	@param silent: suppress error messages
	@type silent: Boolean (integer)
	@rype: list
	@return:
	1.  If each exists, it returns [cat, pkgname, version, rev]
	2.  If cat is not specificed in mydata, cat will be "null"
	3.  if rev does not exist it will be '-r0'
	"""

	try:
		return catcache[mydata]
	except KeyError:
		pass
	mysplit = mydata.split('/', 1)
	p_split=None
	if len(mysplit)==1:
		cat = _missing_cat
		p_split = _pkgsplit(mydata)
	elif len(mysplit)==2:
		cat = mysplit[0]
		if _cat_re.match(cat) is not None:
			p_split = _pkgsplit(mysplit[1])
	if not p_split:
		catcache[mydata]=None
		return None
	retval = (cat, p_split[0], p_split[1], p_split[2])
	catcache[mydata]=retval
	return retval

def pkgsplit(mypkg, silent=1):
	"""
	@param mypkg: either a pv or cpv
	@return:
	1. None if input is invalid.
	2. (pn, ver, rev) if input is pv
	3. (cp, ver, rev) if input is a cpv
	"""
	catpsplit = catpkgsplit(mypkg)
	if catpsplit is None:
		return None
	cat, pn, ver, rev = catpsplit
	if cat is _missing_cat and '/' not in mypkg:
		return (pn, ver, rev)
	else:
		return (cat + '/' + pn, ver, rev)

def cpv_getkey(mycpv):
	"""Calls catpkgsplit on a cpv and returns only the cp."""
	mysplit = catpkgsplit(mycpv)
	if mysplit is not None:
		return mysplit[0] + '/' + mysplit[1]

	warnings.warn("portage.versions.cpv_getkey() " + \
		"called with invalid cpv: '%s'" % (mycpv,),
		DeprecationWarning, stacklevel=2)

	myslash = mycpv.split("/", 1)
	mysplit = _pkgsplit(myslash[-1])
	if mysplit is None:
		return None
	mylen = len(myslash)
	if mylen == 2:
		return myslash[0] + "/" + mysplit[0]
	else:
		return mysplit[0]

def cpv_getversion(mycpv):
	"""Returns the v (including revision) from an cpv."""
	cp = cpv_getkey(mycpv)
	if cp is None:
		return None
	return mycpv[len(cp+"-"):]

def cpv_sort_key():
	"""
	Create an object for sorting cpvs, to be used as the 'key' parameter
	in places like list.sort() or sorted(). This calls catpkgsplit() once for
	each cpv and caches the result. If a given cpv is invalid or two cpvs
	have different category/package names, then plain string (> and <)
	comparison is used.

	@rtype: key object for sorting
	@return: object for use as the 'key' parameter in places like
		list.sort() or sorted()
	"""

	split_cache = {}

	def cmp_cpv(cpv1, cpv2):

		split1 = split_cache.get(cpv1, False)
		if split1 is False:
			split1 = catpkgsplit(cpv1)
			if split1 is not None:
				split1 = (split1[:2], '-'.join(split1[2:]))
			split_cache[cpv1] = split1

		split2 = split_cache.get(cpv2, False)
		if split2 is False:
			split2 = catpkgsplit(cpv2)
			if split2 is not None:
				split2 = (split2[:2], '-'.join(split2[2:]))
			split_cache[cpv2] = split2

		if split1 is None or split2 is None or split1[0] != split2[0]:
			return (cpv1 > cpv2) - (cpv1 < cpv2)

		return vercmp(split1[1], split2[1])

	return cmp_sort_key(cmp_cpv)

def catsplit(mydep):
        return mydep.split("/", 1)

def best(mymatches):
	"""Accepts None arguments; assumes matches are valid."""
	if not mymatches:
		return ""
	if len(mymatches) == 1:
		return mymatches[0]
	bestmatch = mymatches[0]
	p2 = catpkgsplit(bestmatch)[1:]
	for x in mymatches[1:]:
		p1 = catpkgsplit(x)[1:]
		if pkgcmp(p1, p2) > 0:
			bestmatch = x
			p2 = catpkgsplit(bestmatch)[1:]
	return bestmatch
