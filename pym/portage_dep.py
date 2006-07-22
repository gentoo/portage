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

import os,string,types,sys,copy
import portage_exception
from portage_versions import catpkgsplit, catsplit, pkgcmp, pkgsplit, ververify

def strip_empty(myarr):
	for x in range(len(myarr)-1, -1, -1):
		if not myarr[x]:
			del myarr[x]
	return myarr

def paren_reduce(mystr,tokenize=1):
	"Accepts a list of strings, and converts '(' and ')' surrounded items to sub-lists"
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

def paren_enclose(mylist):
	mystrparts = []
	for x in mylist:
		if isinstance(x, list):
			mystrparts.append("( "+paren_enclose(x)+" )")
		else:
			mystrparts.append(x)
	return " ".join(mystrparts)

def use_reduce(deparray, uselist=[], masklist=[], matchall=0, excludeall=[]):
	"""Takes a paren_reduce'd array and reduces the use? conditionals out
	leaving an array with subarrays
	"""
	# Quick validity checks
	for x in range(len(deparray)):
		if deparray[x] in ["||","&&"]:
			if len(deparray) - 1 == x or not isinstance(deparray[x+1], list):
				raise portage_exception.InvalidDependString(deparray[x]+" missing atom list in \""+paren_enclose(deparray)+"\"")
	if deparray and deparray[-1] and deparray[-1][-1] == "?":
		raise portage_exception.InvalidDependString("Conditional without target in \""+paren_enclose(deparray)+"\"")
	
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
			#	raise portage_exception.InvalidDependString("No default atom(s) in \""+paren_enclose(deparray)+"\"")
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
					sys.stderr.write("  --> "+string.join(map(str,[head]+newdeparray))+"\n")

				# Check that each flag matches
				ismatch = True
				for head in newdeparray[:-1]:
					head = head[:-1]
					if head[0] == "!":
						head = head[1:]
						if not matchall and head in uselist or head in excludeall:
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
					else:
						rlist += [target]

			else:
				rlist += [head]

	return rlist


def dep_opconvert(deplist):
	"""Move || and && to the beginning of the following arrays"""
	# Hack in management of the weird || for dep_wordreduce, etc.
	# dep_opconvert: [stuff, ["||", list, of, things]]
	# At this point: [stuff, "||", [list, of, things]]
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
	returns '~', '=', '>', '<', '=*', '>=', or '<='
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

def dep_getcpv(mydep):
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
	return mydep

def isvalidatom(atom):
	mycpv_cps = catpkgsplit(dep_getcpv(atom))
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
	myparts = mypkg.split('-')
	for x in myparts:
		if ververify(x):
			return 0
	return 1

iscache = {}

def isspecific(mypkg):
	"now supports packages with no category"
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
	if mydep and isspecific(mydep):
		mysplit = catpkgsplit(mydep)
		if not mysplit:
			return mydep
		return mysplit[0] + "/" + mysplit[1]
	else:
		return mydep

def match_to_list(mypkg, mylist):
	"""(pkgname, list)
	Searches list for entries that matches the package.
	"""
	matches = []
	for x in mylist:
		if match_from_list(x, [mypkg]):
			if x not in matches:
				matches.append(x)
	return matches

def best_match_to_list(mypkg, mylist):
	"""(pkgname, list)
	Returns the most specific entry (assumed to be the longest one)
	that matches the package given.
	"""
	# XXX Assumption is wrong sometimes.
	maxlen = 0
	bestm  = None
	for x in match_to_list(mypkg, mylist):
		if len(x) > maxlen:
			maxlen = len(x)
			bestm  = x
	return bestm

def match_from_list(mydep, candidate_list):
	from portage_util import writemsg
	if mydep[0] == "!":
		mydep = mydep[1:]

	mycpv     = dep_getcpv(mydep)
	mycpv_cps = catpkgsplit(mycpv) # Can be None if not specific

	if not mycpv_cps:
		cat, pkg = catsplit(mycpv)
		ver      = None
		rev      = None
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
				if x != mycpv:
					continue
			elif xs[0] != mycpv:
				continue
			mylist.append(x)

	elif operator == "=": # Exact match
		if mycpv in candidate_list:
			mylist = [mycpv]

	elif operator == "=*": # glob match
		# The old verion ignored _tag suffixes... This one doesn't.
		for x in candidate_list:
			if x[0:len(mycpv)] == mycpv:
				mylist.append(x)

	elif operator == "~": # version, any revision, match
		for x in candidate_list:
			xs = catpkgsplit(x)
			if xs[0:2] != mycpv_cps[0:2]:
				continue
			if xs[2] != ver:
				continue
			mylist.append(x)

	elif operator in [">", ">=", "<", "<="]:
		for x in candidate_list:
			try:
				result = pkgcmp(pkgsplit(x), [cat + "/" + pkg, ver, rev])
			except SystemExit:
				raise
			except:
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

	return mylist
