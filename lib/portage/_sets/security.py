# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage.glsa as glsa
from portage._sets.base import PackageSet
from portage.versions import vercmp
from portage._sets import get_boolean

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
		self._least_change = least_change

	def getGlsaList(self, skip_applied):
		glsaindexlist = glsa.get_glsa_list(self._settings)
		if skip_applied:
			applied_list = glsa.get_applied_glsas(self._settings)
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
				atomlist += ["="+x for x in myglsa.getMergeList(least_change=self._least_change)]
		self._setAtoms(self._reduce(atomlist))

	def _reduce(self, atomlist):
		mydict = {}
		for atom in atomlist[:]:
			cpv = self._portdbapi.xmatch("match-all", atom)[0]
			pkg = self._portdbapi._pkg_str(cpv, None)
			cps = "%s:%s" % (pkg.cp, pkg.slot)
			if not cps in mydict:
				mydict[cps] = (atom, cpv)
			else:
				other_cpv = mydict[cps][1]
				if vercmp(cpv.version, other_cpv.version) > 0:
					atomlist.remove(mydict[cps][0])
					mydict[cps] = (atom, cpv)
		return atomlist

	def useGlsa(self, myglsa):
		return True

	def updateAppliedList(self):
		glsaindexlist = self.getGlsaList(True)
		applied_list = glsa.get_applied_glsas(self._settings)
		for glsaid in glsaindexlist:
			myglsa = glsa.Glsa(glsaid, self._settings, self._vardbapi, self._portdbapi)
			if not myglsa.isVulnerable() and not myglsa.nr in applied_list:
				myglsa.inject()

	def singleBuilder(cls, options, settings, trees):
		least_change = not get_boolean(options, "use_emerge_resolver", False)
		return cls(settings, trees["vartree"].dbapi, trees["porttree"].dbapi, least_change=least_change)
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
