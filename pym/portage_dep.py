# deps.py -- Portage dependency resolution functions
# Copyright 2003-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/portage_dep.py,v 1.15.2.3 2005/04/02 14:07:59 jstubbs Exp $


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

def use_reduce(deparray, uselist=[], masklist=[], matchall=0, excludeall=[]):
	"""Takes a paren_reduce'd array and reduces the use? conditionals out
	leaving an array with subarrays
	"""
	# Quick validity checks
	for x in range(1,len(deparray)):
		if deparray[x] in ["||","&&"]:
			if len(deparray) == x:
				# Operator is the last element
				raise portage_exception.InvalidDependString("INVALID "+deparray[x]+" DEPEND STRING: "+str(deparray))
			if type(deparray[x+1]) != types.ListType:
				# Operator is not followed by a list
				raise portage_exception.InvalidDependString("INVALID "+deparray[x]+" DEPEND STRING: "+str(deparray))
	if deparray and deparray[-1] and deparray[-1][-1] == "?":
		# Conditional with no target
		raise portage_exception.InvalidDependString("INVALID "+deparray[x]+" DEPEND STRING: "+str(deparray))
	
	#XXX: Compatibility -- Still required?
	if ("*" in uselist):
		matchall=1
	
	mydeparray = deparray[:]
	rlist = []
	while mydeparray:
		head = mydeparray.pop(0)

		if type(head) == types.ListType:
			rlist = rlist + [use_reduce(head, uselist, masklist, matchall, excludeall)]

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
						rlist += [use_reduce(target, uselist, masklist, matchall, excludeall)]
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
