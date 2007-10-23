# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
import portage.glsa as glsa
from portage.util import grabfile, write_atomic
from portage.const import CACHE_PATH
from portage.sets.base import PackageSet

__all__ = ["SecuritySet", "NewGlsaSet", "NewAffectedSet", "AffectedSet"]

class SecuritySet(PackageSet):
	_operations = ["merge"]
	_skip_applied = False
	
	description = "package set that includes all packages possibly affected by a GLSA"
		
	def __init__(self, settings, vardbapi, portdbapi, least_change=True):
		super(SecuritySet, self).__init__()
		self._settings = settings
		self._vardbapi = vardbapi
		self._portdbapi = portdbapi
		self._checkfile = os.path.join(os.sep, self._settings["ROOT"], CACHE_PATH.lstrip(os.sep), "glsa")
		self._least_change = least_change

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
				atomlist += myglsa.getMergeList(least_change=self._least_change)
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
	
	def singleBuilder(cls, options, setconfig):
		if "use_emerge_resoler" in options \
				and options.get("use_emerge_resolver").lower() in ["1", "yes", "true", "on"]:
			least_change = False
		else:
			least_change = True
		return cls(setconfig.settings, setconfig.trees["vartree"].dbapi, \
					setconfig.trees["porttree"].dbapi, least_change=least_change)
	singleBuilder = classmethod(singleBuilder)
	
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
