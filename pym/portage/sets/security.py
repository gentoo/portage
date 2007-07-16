# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage.glsa as glsa

from portage.sets import PackageSet

class SecuritySet(PackageSet):
	_operations = ["merge"]

	def __init__(self, name, settings, vardbapi, portdbapi):
		super(SecuritySet, self).__init__(name)
		self._settings = settings
		self._vardbapi = vardbapi
		self._portdbapi = portdbapi
		
	def load(self):
		glsaindexlist = glsa.get_glsa_list(self._settings)
		atomlist = []
		for glsaid in glsaindexlist:
			myglsa = glsa.Glsa(glsaid, self._settings, self._vardbapi, self._portdbapi)
			#print glsaid, myglsa.isVulnerable(), myglsa.isApplied(), myglsa.getMergeList()
			if self.useGlsa(myglsa):
				atomlist += myglsa.getMergeList(least_change=False)
		self._setAtoms(atomlist)
	
	def useGlsa(self, myglsa):
		return True
	
class NewGlsaSet(SecuritySet):
	def useGlsa(self, myglsa):
		return not myglsa.isApplied()

class AffectedSet(SecuritySet):
	def useGlsa(self, myglsa):
		return myglsa.isVulnerable()
