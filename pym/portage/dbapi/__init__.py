# Copyright 1998-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
import re
from portage.dep import dep_getslot, dep_getkey, match_from_list
from portage.locks import unlockfile
from portage.output import red
from portage.util import writemsg
from portage import dep_expand
from portage.versions import catpkgsplit, catsplit, pkgcmp


class dbapi(object):
	_category_re = re.compile(r'^[+\w][-\.+\w]*$')
	def __init__(self):
		pass

	def close_caches(self):
		pass

	def cp_list(self, cp, use_cache=1):
		return

	def _cpv_sort_ascending(self, cpv_list):
		"""
		Use this to sort self.cp_list() results in ascending
		order. It sorts in place and returns None.
		"""
		if len(cpv_list) > 1:
			# If the cpv includes explicit -r0, it has to be preserved
			# for consistency in findname and aux_get calls, so use a
			# dict to map strings back to their original values.
			str_map = {}
			for i, cpv in enumerate(cpv_list):
				mysplit = tuple(catpkgsplit(cpv)[1:])
				str_map[mysplit] = cpv
				cpv_list[i] = mysplit
			cpv_list.sort(pkgcmp)
			for i, mysplit in enumerate(cpv_list):
				cpv_list[i] = str_map[mysplit]

	def cpv_all(self):
		"""Return all CPVs in the db
		Args:
			None
		Returns:
			A list of Strings, 1 per CPV

		This function relies on a subclass implementing cp_all, this is why the hasattr is there
		"""

		if not hasattr(self, "cp_all"):
			raise NotImplementedError
		cpv_list = []
		for cp in self.cp_all():
			cpv_list.extend(self.cp_list(cp))
		return cpv_list

	def cp_all(self):
		""" Implement this in a child class
		Args
			None
		Returns:
			A list of strings 1 per CP in the datastore
		"""
		return NotImplementedError

	def aux_get(self, mycpv, mylist):
		"""Return the metadata keys in mylist for mycpv
		Args:
			mycpv - "sys-apps/foo-1.0"
			mylist - ["SLOT","DEPEND","HOMEPAGE"]
		Returns: 
			a list of results, in order of keys in mylist, such as:
			["0",">=sys-libs/bar-1.0","http://www.foo.com"] or [] if mycpv not found'
		"""
		raise NotImplementedError
	
	def aux_update(self, cpv, metadata_updates):
		"""
		Args:
		  cpv - "sys-apps/foo-1.0"
			metadata_updates = { key : newvalue }
		Returns:
			None
		"""
		raise NotImplementedError

	def match(self, origdep, use_cache=1):
		"""Given a dependency, try to find packages that match
		Args:
			origdep - Depend atom
			use_cache - Boolean indicating if we should use the cache or not
			NOTE: Do we ever not want the cache?
		Returns:
			a list of packages that match origdep
		"""
		mydep = dep_expand(origdep, mydb=self, settings=self.settings)
		mykey = dep_getkey(mydep)
		mylist = match_from_list(mydep, self.cp_list(mykey, use_cache=use_cache))
		myslot = dep_getslot(mydep)
		if myslot is not None:
			mylist = [cpv for cpv in mylist \
				if self.aux_get(cpv, ["SLOT"])[0] == myslot]
		return mylist

	def invalidentry(self, mypath):
		if mypath.endswith('portage_lockfile'):
			if not os.environ.has_key("PORTAGE_MASTER_PID"):
				writemsg("Lockfile removed: %s\n" % mypath, 1)
				unlockfile((mypath, None, None))
			else:
				# Nothing we can do about it. We're probably sandboxed.
				pass
		elif '/-MERGING-' in mypath:
			if os.path.exists(mypath):
				writemsg(red("INCOMPLETE MERGE:")+" "+mypath+"\n", noiselevel=-1)
		else:
			writemsg("!!! Invalid db entry: %s\n" % mypath, noiselevel=-1)

	def update_ents(self, updates, onProgress=None):
		"""
		Update metadata of all packages for package moves.
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
		"""This function takes a sequence:
		Args:
			mylist: a sequence of (package, originalslot, newslot)
		Returns:
			The number of slotmoves this function did
		"""
		pkg = mylist[1]
		origslot = mylist[2]
		newslot = mylist[3]
		origmatches = self.match(pkg)
		moves = 0
		if not origmatches:
			return moves
		for mycpv in origmatches:
			slot = self.aux_get(mycpv, ["SLOT"])[0]
			if slot != origslot:
				continue
			moves += 1
			mydata = {"SLOT": newslot+"\n"}
			self.aux_update(mycpv, mydata)
		return moves
