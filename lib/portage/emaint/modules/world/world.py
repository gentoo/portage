# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os


class WorldHandler:

	short_desc = "Fix problems in the world file"

	@staticmethod
	def name():
		return "world"

	def __init__(self):
		self.invalid = []
		self.not_installed = []
		self.okay = []
		from portage._sets import load_default_config
		setconfig = load_default_config(portage.settings,
			portage.db[portage.settings['EROOT']])
		self._sets = setconfig.getSets()

	def _check_world(self, onProgress):
		eroot = portage.settings['EROOT']
		self.world_file = os.path.join(eroot, portage.const.WORLD_FILE)
		self.found = os.access(self.world_file, os.R_OK)
		vardb = portage.db[eroot]["vartree"].dbapi

		from portage._sets import SETPREFIX
		sets = self._sets
		world_atoms = list(sets["selected"])
		maxval = len(world_atoms)
		if onProgress:
			onProgress(maxval, 0)
		for i, atom in enumerate(world_atoms):
			if not isinstance(atom, portage.dep.Atom):
				if atom.startswith(SETPREFIX):
					s = atom[len(SETPREFIX):]
					if s in sets:
						self.okay.append(atom)
					else:
						self.not_installed.append(atom)
				else:
					self.invalid.append(atom)
				if onProgress:
					onProgress(maxval, i+1)
				continue
			okay = True
			if not vardb.match(atom):
				self.not_installed.append(atom)
				okay = False
			if okay:
				self.okay.append(atom)
			if onProgress:
				onProgress(maxval, i+1)

	def check(self, **kwargs):
		onProgress = kwargs.get('onProgress', None)
		self._check_world(onProgress)
		errors = []
		if self.found:
			errors += ["'%s' is not a valid atom" % x for x in self.invalid]
			errors += ["'%s' is not installed" % x for x in self.not_installed]
		else:
			errors.append(self.world_file + " could not be opened for reading")
		if errors:
			return (False, errors)
		return (True, None)

	def fix(self, **kwargs):
		onProgress = kwargs.get('onProgress', None)
		world_set = self._sets["selected"]
		world_set.lock()
		try:
			world_set.load() # maybe it's changed on disk
			before = set(world_set)
			self._check_world(onProgress)
			after = set(self.okay)
			errors = []
			if before != after:
				try:
					world_set.replace(self.okay)
				except portage.exception.PortageException:
					errors.append("%s could not be opened for writing" % \
						self.world_file)
			if errors:
				return (False, errors)
			return (True, None)
		finally:
			world_set.unlock()
