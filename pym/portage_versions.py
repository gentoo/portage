# portage_versions.py -- core Portage functionality
# Copyright 1998-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import re,string

ver_regexp = re.compile("^(cvs\\.)?(\\d+)((\\.\\d+)*)([a-z]?)((_(pre|p|beta|alpha|rc)\\d*)*)(-r(\\d+))?$")
suffix_regexp = re.compile("^(alpha|beta|rc|pre|p)(\\d*)$")
suffix_value = {"pre": -2, "p": 0, "alpha": -4, "beta": -3, "rc": -1}
endversion_keys = ["pre", "p", "alpha", "beta", "rc"]


def ververify(myver, silent=1):
	if ver_regexp.match(myver):
		return 1
	else:
		if not silent:
			print "!!! syntax error in version: %s" % myver
		return 0

vercmp_cache = {}
def vercmp(ver1, ver2, silent=1):
	"""
	Compare two versions
	Example usage:
		>>> from portage_versions import vercmp
		>>> vercmp('1.0-r1','1.2-r3')
		negative number
		>>> vercmp('1.3','1.2-r3')
		positive number
		>>> vercmp('1.0_p3','1.0_p3')
		0
	
	@param pkg1: version to compare with (see ver_regexp in portage_versions.py)
	@type pkg1: string (example: "2.1.2-r3")
	@param pkg2: version to compare againts (see ver_regexp in portage_versions.py)
	@type pkg2: string (example: "2.1.2_rc5")
	@rtype: None or float
	@return:
	1. positive if ver1 is greater than ver2
	2. negative if ver1 is less than ver2 
	3. 0 if ver1 equals ver2
	4. None if ver1 or ver2 are invalid (see ver_regexp in portage_versions.py)
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
			print "!!! syntax error in version: %s" % ver1
		return None
	if not match2 or not match2.groups():
		if not silent:
			print "!!! syntax error in version: %s" % ver2
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
	list1 = [string.atoi(match1.group(2))]
	list2 = [string.atoi(match2.group(2))]
	
	# this part would greatly benefit from a fixed-length version pattern
	if len(match1.group(3)) or len(match2.group(3)):
		vlist1 = match1.group(3)[1:].split(".")
		vlist2 = match2.group(3)[1:].split(".")
		for i in range(0, max(len(vlist1), len(vlist2))):
			# Implcit .0 is given a value of -1, so that 1.0.0 > 1.0, since it
			# would be ambiguous if two versions that aren't literally equal
			# are given the same value (in sorting, for example).
			if len(vlist1) <= i or len(vlist1[i]) == 0:
				list1.append(-1)
				list2.append(string.atoi(vlist2[i]))
			elif len(vlist2) <= i or len(vlist2[i]) == 0:
				list1.append(string.atoi(vlist1[i]))
				list2.append(-1)
			# Let's make life easy and use integers unless we're forced to use floats
			elif (vlist1[i][0] != "0" and vlist2[i][0] != "0"):
				list1.append(string.atoi(vlist1[i]))
				list2.append(string.atoi(vlist2[i]))
			# now we have to use floats so 1.02 compares correctly against 1.1
			else:
				list1.append(string.atof("0."+vlist1[i]))
				list2.append(string.atof("0."+vlist2[i]))

	# and now the final letter
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
			vercmp_cache[mykey] = list1[i] - list2[i]
			return list1[i] - list2[i]
	
	# main version is equal, so now compare the _suffix part
	list1 = match1.group(6).split("_")[1:]
	list2 = match2.group(6).split("_")[1:]
	
	for i in range(0, max(len(list1), len(list2))):
		if len(list1) <= i:
			s1 = ("p","0")
		else:
			s1 = suffix_regexp.match(list1[i]).groups()
		if len(list2) <= i:
			s2 = ("p","0")
		else:
			s2 = suffix_regexp.match(list2[i]).groups()
		if s1[0] != s2[0]:
			return suffix_value[s1[0]] - suffix_value[s2[0]]
		if s1[1] != s2[1]:
			# it's possible that the s(1|2)[1] == ''
			# in such a case, fudge it.
			try:			r1 = string.atoi(s1[1])
			except ValueError:	r1 = 0
			try:			r2 = string.atoi(s2[1])
			except ValueError:	r2 = 0
			return r1 - r2
	
	# the suffix part is equal to, so finally check the revision
	if match1.group(10):
		r1 = string.atoi(match1.group(10))
	else:
		r1 = 0
	if match2.group(10):
		r2 = string.atoi(match2.group(10))
	else:
		r2 = 0
	vercmp_cache[mykey] = r1 - r2
	return r1 - r2
	
def pkgcmp(pkg1, pkg2):
	"""
	Compare 2 package versions created in pkgsplit format.

	Example usage:
		>>> from portage_versions import *
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
	mycmp=vercmp(pkg1[1],pkg2[1])
	if mycmp>0:
		return 1
	if mycmp<0:
		return -1
	r1=string.atof(pkg1[2][1:])
	r2=string.atof(pkg2[2][1:])
	if r1>r2:
		return 1
	if r2>r1:
		return -1
	return 0


pkgcache={}

def pkgsplit(mypkg,silent=1):
	try:
		if not pkgcache[mypkg]:
			return None
		return pkgcache[mypkg][:]
	except KeyError:
		pass
	myparts=string.split(mypkg,'-')
	
	if len(myparts)<2:
		if not silent:
			print "!!! Name error in",mypkg+": missing a version or name part."
		pkgcache[mypkg]=None
		return None
	for x in myparts:
		if len(x)==0:
			if not silent:
				print "!!! Name error in",mypkg+": empty \"-\" part."
			pkgcache[mypkg]=None
			return None
	
	#verify rev
	revok=0
	myrev=myparts[-1]
	if len(myrev) and myrev[0]=="r":
		try:
			string.atoi(myrev[1:])
			revok=1
		except: 
			pass
	if revok:
		verPos = -2
		revision = myparts[-1]
	else:
		verPos = -1
		revision = "r0"

	if ververify(myparts[verPos]):
		if len(myparts)== (-1*verPos):
			pkgcache[mypkg]=None
			return None
		else:
			for x in myparts[:verPos]:
				if ververify(x):
					pkgcache[mypkg]=None
					return None
					#names can't have versiony looking parts
			myval=[string.join(myparts[:verPos],"-"),myparts[verPos],revision]
			pkgcache[mypkg]=myval
			return myval
	else:
		pkgcache[mypkg]=None
		return None

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
	4.  If cat is invalid (specified but has incorrect syntax)
 		a ValueError will be thrown
	"""
	
	# Categories may contain a-zA-z0-9+_- but cannot start with -
	valid_category = re.compile("^[A-Za-z0-9+_][A-Za-z0-9+_-]*")
	try:
		if not catcache[mydata]:
			return None
		return catcache[mydata][:]
	except KeyError:
		pass
	mysplit=mydata.split("/")
	p_split=None
	if len(mysplit)==1:
		retval=["null"]
		p_split=pkgsplit(mydata,silent=silent)
	elif len(mysplit)==2:
		if not valid_category.match(mysplit[0]):
			raise ValueError("Invalid category in %s" %mydata )
		retval=[mysplit[0]]
		p_split=pkgsplit(mysplit[1],silent=silent)
	if not p_split:
		catcache[mydata]=None
		return None
	retval.extend(p_split)
	catcache[mydata]=retval
	return retval

def catsplit(mydep):
        return mydep.split("/", 1)

def best(mymatches):
	"""Accepts None arguments; assumes matches are valid."""
	if mymatches is None:
		return ""
	if not len(mymatches):
		return ""
	bestmatch = mymatches[0]
	p2 = catpkgsplit(bestmatch)[1:]
	for x in mymatches[1:]:
		p1 = catpkgsplit(x)[1:]
		if pkgcmp(p1, p2) > 0:
			bestmatch = x
			p2 = catpkgsplit(bestmatch)[1:]
	return bestmatch
