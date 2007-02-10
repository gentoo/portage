#!/usr/bin/python
# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os,sys,re

try:
	import portage
except ImportError:
	from os import path as osp
	sys.path.insert(0, osp.join(osp.dirname(osp.dirname(__file__)), "pym"))
	import portage

from stat import *
from portage.output import *
from portage import lockfile,unlockfile,VDB_PATH,root


mylog = open("/var/log/emerge_fix-db.log", "a")
def writemsg(msg):
	if msg[-1] != '\n':
		msg += "\n"
	sys.stderr.write(msg)
	sys.stderr.flush()
	mylog.write(msg)
	mylog.flush()

def fix_global_counter(value):
	myf = open("/var/cache/edb/counter")
	newvalue = value+1000
	myf.write(str(newvalue))
	myf.flush()
	myf.close()
	return newvalue

bad = {}
counters = {}
times = {}

try:
	real_counter = long(open("/var/cache/edb/counter").read())
except SystemExit, e:
	raise  # This needs to be propogated
except:
	writemsg("ERROR: Real counter is invalid.\n")
	real_counter = 0

vardbdir = root+VDB_PATH+"/"
for cat in os.listdir(vardbdir):
	catdir = vardbdir+cat+"/"
	if not os.path.isdir(catdir):
		writemsg("Invalid file: '%s'\n" % catdir[:-1])
		continue
	for pkg in os.listdir(catdir):
		pkgdir = catdir+pkg+"/"
		catpkg = cat+"/"+pkg

		if not os.path.isdir(catdir):
			writemsg("Invalid file: '%s'\n" % pkgdir)
			continue
			
		bad[catpkg] = []
		
		pkgdirlist = os.listdir(pkgdir)
		if not pkgdirlist:
			writemsg("ERROR: Package directory is empty for '%s'\n" % catpkg)
			writemsg("       Deleting this directory. Remerge if you want it back.\n")
			os.rmdir(pkgdir)
			del bad[catpkg]
			continue
		
		if "CONTENTS" not in pkgdirlist:
			bad[catpkg] += ["CONTENTS is missing"]
			times[catpkg] = -1
			writemsg("ERROR: Contents file is missing from the package directory.\n")
			writemsg("       '%s' is corrupt and should be deleted.\n" % catpkg)
		else:
			times[catpkg] = None
			for line in open(pkgdir+"CONTENTS").readlines():
				mysplit = line.split()
				if mysplit[0] == "obj":
					try:
						times[catpkg] = long(mysplit[-1])
					except SystemExit, e:
						raise  # This needs to be propogated
					except:
						times[catpkg] = -1
						bad[catpkg] += ["CONTENTS is corrupt"]
						writemsg("ERROR: Corrupt CONTENTS file in '%s'\n" % catpkg)
						writemsg("       This package should be deleted.\n")
					break
			if times[catpkg] == None:
				times[catpkg] = os.stat(pkgdir+"CONTENTS")[ST_MTIME]

		if "COUNTER" not in pkgdirlist:
			bad[catpkg] += ["COUNTER is missing"]
			writemsg("ERROR: COUNTER file missing from '%s'.\n" % catpkg)
			counters[catpkg] = -1
		else:
			try:
				counters[catpkg] = long(open(pkgdir+"COUNTER").read().strip())
				if counters[catpkg] > real_counter:
					writemsg("ERROR: Global counter is lower than the '%s' COUNTER." % catpkg)
					real_counter = fix_global_counter(counters[catpkg])
			except SystemExit, e:
				raise  # This needs to be propogated
			except:
				bad[catpkg] += ["COUNTER is corrupt"]
				counters[catpkg] = -1

		if "SLOT" not in pkgdirlist:
			writemsg("ERROR: SLOT file missing from '%s'.\n" % catpkg)
			writemsg("       RE-MERGE this exact package version or unmerge and remerge.\n")
			bad[catpkg] += ["SLOT is missing"]
		else:
			myslot = open(pkgdir+"SLOT").read()
			if myslot and myslot[-1]=="\n":
				#writemsg("WARN: SLOT file has a newline. '%s'\n" % catpkg)
				myslot = myslot[:-1]
			if not myslot:
				bad[catpkg] += ["SLOT is empty"]
				writemsg("ERROR: SLOT file is empty for '%s'.\n" % catpkg)
				writemsg("       RE-MERGE this exact package version or unmerge and remerge it.\n")
			elif re.search("[^-a-zA-Z0-9\._]", myslot):
				bad[catpkg] += ["SLOT is corrupt"]
				writemsg("ERROR: SLOT file is corrupt for '%s'.\n" % catpkg)
				writemsg("       RE-MERGE this exact package version or unmerge and remerge it.\n")
			elif myslot.strip() != myslot:
				writemsg("WARN: SLOT file has invalid characters. '%s'\n" % catpkg)
				bad[catpkg] += ["SLOT is invalid"]

		if not bad[catpkg]:
			del bad[catpkg]


actions = {}
writemsg("\n\n")
for catpkg in bad.keys():
	bad[catpkg].sort()

	mystr = ""
	for x in bad[catpkg]:
		mystr += "   "+str(x)+"\n"

	if bad[catpkg] == ["CONTENTS is missing", "SLOT is missing"]:
		writemsg("%s: (possibly injected)\n%s\n" % (green(catpkg), mystr))
		actions[catpkg] = ["ignore"]
	elif bad[catpkg] == ["SLOT is empty"]:
		writemsg("%s: (old package) []\n%s\n" % (yellow(catpkg), mystr))
		actions[catpkg] = ["remerge"]
	else:
		writemsg("%s: (damaged/invalid) []\n%s\n" % (red(catpkg), mystr))
		actions[catpkg] = ["merge exact"]

if (len(sys.argv) > 1) and (sys.argv[1] == "--fix"):
	writemsg("These are only directions, at the moment.")
	for catpkg in actions.keys():
		action = actions[catpkg]
		writemsg("We will now '%s' '%s'..." % (action, catpkg))
		#if action == 
else:
	#writemsg("Run with '--fix' to attempt automatic correction.")
	pass

















