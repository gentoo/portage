# Copyright 1998-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


from portage.dep import dep_getslot, dep_getkey, match_from_list
from portage.locks import unlockfile
from portage.output import red
from portage.util import writemsg

from portage import dep_expand

import os, re

class dbapi(object):
	def __init__(self):
		pass

	def close_caches(self):
		pass

	def cp_list(self, cp, use_cache=1):
		return

	def cpv_all(self):
		cpv_list = []
		for cp in self.cp_all():
			cpv_list.extend(self.cp_list(cp))
		return cpv_list

	def aux_get(self, mycpv, mylist):
		"stub code for returning auxiliary db information, such as SLOT, DEPEND, etc."
		'input: "sys-apps/foo-1.0",["SLOT","DEPEND","HOMEPAGE"]'
		'return: ["0",">=sys-libs/bar-1.0","http://www.foo.com"] or [] if mycpv not found'
		raise NotImplementedError

	def match(self, origdep, use_cache=1):
		mydep = dep_expand(origdep, mydb=self, settings=self.settings)
		mykey = dep_getkey(mydep)
		mylist = match_from_list(mydep, self.cp_list(mykey, use_cache=use_cache))
		myslot = dep_getslot(mydep)
		if myslot is not None:
			mylist = [cpv for cpv in mylist \
				if self.aux_get(cpv, ["SLOT"])[0] == myslot]
		return mylist

	def invalidentry(self, mypath):
		if re.search("portage_lockfile$", mypath):
			if not os.environ.has_key("PORTAGE_MASTER_PID"):
				writemsg("Lockfile removed: %s\n" % mypath, 1)
				unlockfile((mypath, None, None))
			else:
				# Nothing we can do about it. We're probably sandboxed.
				pass
		elif re.search(".*/-MERGING-(.*)", mypath):
			if os.path.exists(mypath):
				writemsg(red("INCOMPLETE MERGE:")+" "+mypath+"\n", noiselevel=-1)
		else:
			writemsg("!!! Invalid db entry: %s\n" % mypath, noiselevel=-1)

	def update_ents(self, updates, onProgress=None):
		"""
		Update metadata of all packages for packages moves.
		@param updates: A list of move commands
		@type updates: List
		@param onProgress: A progress callback function
		@type onProgress: a callable that takes 2 integer arguments: maxval and curval
		"""
		cpv_all = self.cpv_all()
		cpv_all.sort()
		maxval = len(cpv_all)
		aux_get = self.aux_get
		aux_update = self.aux_update
		update_keys = ["DEPEND", "RDEPEND", "PDEPEND", "PROVIDE"]
		from itertools import izip
		from portage.update import update_dbentries
		if onProgress:
			onProgress(maxval, 0)
		for i, cpv in enumerate(cpv_all):
			metadata = dict(izip(update_keys, aux_get(cpv, update_keys)))
			metadata_updates = update_dbentries(updates, metadata)
			if metadata_updates:
				aux_update(cpv, metadata_updates)
			if onProgress:
				onProgress(maxval, i+1)

	def move_slot_ent(self, mylist):
		pkg = mylist[1]
		origslot = mylist[2]
		newslot = mylist[3]
		origmatches = self.match(pkg)
		moves = 0
		if not origmatches:
			return moves
		from portage.versions import catsplit
		for mycpv in origmatches:
			slot = self.aux_get(mycpv, ["SLOT"])[0]
			if slot != origslot:
				continue
			moves += 1
			mydata = {"SLOT": newslot+"\n"}
			self.aux_update(mycpv, mydata)
		return moves
