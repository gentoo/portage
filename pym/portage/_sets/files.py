# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import errno
import re
from itertools import chain

from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.util import grabfile, write_atomic, ensure_dirs, normalize_path
from portage.const import USER_CONFIG_PATH, WORLD_FILE
from portage.localization import _
from portage.locks import lockfile, unlockfile
from portage import portage_gid
from portage._sets.base import PackageSet, EditablePackageSet
from portage._sets import SetConfigError, SETPREFIX, get_boolean
from portage.env.loaders import ItemFileLoader, KeyListFileLoader
from portage.env.validators import ValidAtomValidator
from portage import cpv_getkey

__all__ = ["WorldSelectedSet",]

class WorldSelectedSet(EditablePackageSet):
	description = "Set of packages that were directly installed by the user"
	
	def __init__(self, root):
		super(WorldSelectedSet, self).__init__()
		# most attributes exist twice as atoms and non-atoms are stored in 
		# separate files
		self._lock = None
		self._filename = os.path.join(os.sep, root, WORLD_FILE)
		self.loader = ItemFileLoader(self._filename, self._validate)
		self._mtime = None

	def _validate(self, atom):
		return ValidAtomValidator(atom)

	def write(self):
		write_atomic(self._filename,
			"".join(sorted("%s\n" % x for x in self._atoms)))

	def load(self):
		atoms = []
		nonatoms = []
		atoms_changed = False
		# load atoms and non-atoms from different files so the worldfile is 
		# backwards-compatible with older versions and other PMs, even though 
		# it's supposed to be private state data :/
		try:
			mtime = os.stat(self._filename).st_mtime
		except (OSError, IOError):
			mtime = None
		if (not self._loaded or self._mtime != mtime):
			try:
				data, errors = self.loader.load()
				for fname in errors:
					for e in errors[fname]:
						self.errors.append(fname+": "+e)
			except EnvironmentError as e:
				if e.errno != errno.ENOENT:
					raise
				del e
				data = {}
			atoms = list(data)
			self._mtime = mtime
			atoms_changed = True
		else:
			atoms.extend(self._atoms)

		if atoms_changed:
			self._setAtoms(atoms+nonatoms)
		
	def _ensure_dirs(self):
		ensure_dirs(os.path.dirname(self._filename), gid=portage_gid, mode=0o2750, mask=0o2)

	def lock(self):
		self._ensure_dirs()
		self._lock = lockfile(self._filename, wantnewlockfile=1)

	def unlock(self):
		unlockfile(self._lock)
		self._lock = None

	def cleanPackage(self, vardb, cpv):
		'''
		Before calling this function you should call lock and load.
		After calling this function you should call unlock.
		'''
		if not self._lock:
			raise AssertionError('cleanPackage needs the set to be locked')

		worldlist = list(self._atoms)
		mykey = cpv_getkey(cpv)
		newworldlist = []
		for x in worldlist:
			if x.cp == mykey:
				matches = vardb.match(x, use_cache=0)
				if not matches:
					#zap our world entry
					pass
				elif len(matches) == 1 and matches[0] == cpv:
					#zap our world entry
					pass
				else:
					#others are around; keep it.
					newworldlist.append(x)
			else:
				#this doesn't match the package we're unmerging; keep it.
				newworldlist.append(x)

		newworldlist.extend(self._nonatoms)
		self.replace(newworldlist)

	def singleBuilder(self, options, settings, trees):
		return WorldSelectedSet(settings["ROOT"])
	singleBuilder = classmethod(singleBuilder)
