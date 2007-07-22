# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage.glsa as glsa
from portage.util import grabfile, write_atomic
from portage.const import CACHE_PATH
import os

from portage.sets import PackageSet

class SecuritySet(PackageSet):
	_operations = ["merge"]
	_skip_applied = False
	
	description = "package set that includes all packages possibly affected by a GLSA"
		
	def __init__(self, name, settings, vardbapi, portdbapi):
		super(SecuritySet, self).__init__(name)
		self._settings = settings
		self._vardbapi = vardbapi
		self._portdbapi = portdbapi
		self._checkfile = os.path.join(os.sep, self._settings["ROOT"], CACHE_PATH.lstrip(os.sep), "glsa")

	def getGlsaList(self, skip_applied):
		glsaindexlist = glsa.get_glsa_list(self._settings)
		if skip_applied:
			applied_list = grabfile(self._checkfile)
			glsaindexlist = set(glsaindexlist).difference(applied_list)
			glsaindexlist = list(glsaindexlist)
		glsaindexlist.sort()
		return glsaindexlist
		
	def load(self):
		glsaindexlist = self.getGlsaList(self._skip_applied)
		atomlist = []
		for glsaid in glsaindexlist:
			myglsa = glsa.Glsa(glsaid, self._settings, self._vardbapi, self._portdbapi)
			#print glsaid, myglsa.isVulnerable(), myglsa.isApplied(), myglsa.getMergeList()
			if self.useGlsa(myglsa):
				atomlist += myglsa.getMergeList(least_change=False)
		self._setAtoms(atomlist)
	
	def useGlsa(self, myglsa):
		return True

	def updateAppliedList(self):
		glsaindexlist = self.getGlsaList(True)
		applied_list = grabfile(self._checkfile)
		for glsaid in glsaindexlist:
			myglsa = glsa.Glsa(glsaid, self._settings, self._vardbapi, self._portdbapi)
			if not myglsa.isVulnerable():
				applied_list.append(glsaid)
		write_atomic(self._checkfile, "\n".join(applied_list))
	
class NewGlsaSet(SecuritySet):
	_skip_applied = True
	description = "Package set that includes all packages possibly affected by an unapplied GLSA"

class AffectedSet(SecuritySet):
	description = "Package set that includes all packages affected by an unapplied GLSA"

	def useGlsa(self, myglsa):
		return myglsa.isVulnerable()

class NewAffectedSet(AffectedSet):
	_skip_applied = True
	description = "Package set that includes all packages affected by an unapplied GLSA"
