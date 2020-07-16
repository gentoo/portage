# -*- coding:utf-8 -*-

from __future__ import print_function

import re
import stat

from _emerge.Package import Package
from _emerge.RootConfig import RootConfig

from repoman.modules.scan.scanbase import ScanBase
# import our initialized portage instance
from repoman._portage import portage
from portage import os
from portage.exception import InvalidPackageName

pv_toolong_re = re.compile(r'[0-9]{19,}')


class Ebuild(ScanBase):
	'''Class to run primary checks on ebuilds'''

	def __init__(self, **kwargs):
		'''Class init

		@param qatracker: QATracker instance
		@param portdb: portdb instance
		@param repo_settings: repository settings instance
		@param vcs_settings: VCSSettings instance
		@param checks: checks dictionary
		'''
		super(Ebuild, self).__init__(**kwargs)
		self.qatracker = kwargs.get('qatracker')
		self.portdb = kwargs.get('portdb')
		self.repo_settings = kwargs.get('repo_settings')
		self.vcs_settings = kwargs.get('vcs_settings')
		self.checks = kwargs.get('checks')
		self.root_config = RootConfig(self.repo_settings.repoman_settings,
			self.repo_settings.trees[self.repo_settings.root], None)
		self.changed = None
		self.xpkg = None
		self.y_ebuild = None
		self.pkg = None
		self.metadata = None
		self.eapi = None
		self.inherited = None
		self.live_ebuild = None
		self.keywords = None
		self.pkgs = {}

	def _set_paths(self, **kwargs):
		repolevel = kwargs.get('repolevel')
		self.relative_path = os.path.join(self.xpkg, self.y_ebuild + ".ebuild")
		self.full_path = os.path.join(self.repo_settings.repodir, self.relative_path)
		self.ebuild_path = self.y_ebuild + ".ebuild"
		if repolevel < 3:
			self.ebuild_path = os.path.join(kwargs.get('pkgdir'), self.ebuild_path)
		if repolevel < 2:
			self.ebuild_path = os.path.join(kwargs.get('catdir'), self.ebuild_path)
		self.ebuild_path = os.path.join(".", self.ebuild_path)

	@property
	def untracked(self):
		'''Determines and returns if the ebuild is not tracked by the vcs'''
		do_check = self.vcs_settings.vcs in ("cvs", "svn", "bzr")
		really_notadded = (self.checks['ebuild_notadded'] and
			self.y_ebuild not in self.vcs_settings.eadded)
		if do_check and really_notadded:
			# ebuild not added to vcs
			return True
		return False

	def check(self, **kwargs):
		'''Perform a changelog and untracked checks on the ebuild

		@param xpkg: Package in which we check (object).
		@param y_ebuild: Ebuild which we check (string).
		@param changed: dictionary instance
		@param repolevel: The depth within the repository
		@param catdir: The category directiory
		@param pkgdir: the package directory
		@returns: dictionary, including {ebuild object}
		'''
		self.xpkg = kwargs.get('xpkg')
		self.y_ebuild = kwargs.get('y_ebuild')
		self.changed = kwargs.get('changed')
		changelog_modified = kwargs.get('changelog_modified')
		self._set_paths(**kwargs)

		if self.checks['changelog'] and not changelog_modified \
			and self.ebuild_path in self.changed.new_ebuilds:
			self.qatracker.add_error('changelog.ebuildadded', self.relative_path)

		if self.untracked:
			# ebuild not added to vcs
			self.qatracker.add_error(
				"ebuild.notadded", self.xpkg + "/" + self.y_ebuild + ".ebuild")
		# update the dynamic data
		dyn_ebuild = kwargs.get('ebuild')
		dyn_ebuild.set(self)
		return False

	def set_pkg_data(self, **kwargs):
		'''Sets some classwide data needed for some of the checks

		@returns: dictionary
		'''
		self.pkg = self.pkgs[self.y_ebuild]
		self.metadata = self.pkg._metadata
		self.eapi = self.metadata["EAPI"]
		self.inherited = self.pkg.inherited
		self.live_ebuild = "live" in self.metadata["PROPERTIES"].split()
		self.keywords = self.metadata["KEYWORDS"].split()
		self.archs = set(kw.lstrip("~") for kw in self.keywords if not kw.startswith("-"))
		return False

	def bad_split_check(self, **kwargs):
		'''Checks for bad category/package splits.

		@param pkgdir: string: path
		@returns: dictionary
		'''
		pkgdir = kwargs.get('pkgdir')
		myesplit = portage.pkgsplit(self.y_ebuild)
		is_bad_split = myesplit is None or myesplit[0] != self.xpkg.split("/")[-1]
		if is_bad_split:
			is_pv_toolong = pv_toolong_re.search(myesplit[1])
			is_pv_toolong2 = pv_toolong_re.search(myesplit[2])
			if is_pv_toolong or is_pv_toolong2:
				self.qatracker.add_error(
					"ebuild.invalidname", self.xpkg + "/" + self.y_ebuild + ".ebuild")
				return True
		elif myesplit[0] != pkgdir:
			print(pkgdir, myesplit[0])
			self.qatracker.add_error(
				"ebuild.namenomatch", self.xpkg + "/" + self.y_ebuild + ".ebuild")
			return True
		return False

	def pkg_invalid(self, **kwargs):
		'''Sets some pkg info and checks for invalid packages

		@param validity_future: Future instance
		@returns: dictionary, including {pkg object}
		'''
		fuse = kwargs.get('validity_future')
		dyn_pkg = kwargs.get('pkg')
		if self.pkg.invalid:
			for k, msgs in self.pkg.invalid.items():
				for msg in msgs:
					self.qatracker.add_error(k, "%s: %s" % (self.relative_path, msg))
			# update the dynamic data
			fuse.set(False, ignore_InvalidState=True)
			dyn_pkg.set(self.pkg)
			return True
		# update the dynamic data
		dyn_pkg.set(self.pkg)
		return False

	def check_isebuild(self, **kwargs):
		'''Test the file for qualifications that is is an ebuild

		@param checkdirlist: list of files in the current package directory
		@param checkdir: current package directory path
		@param xpkg: current package directory being checked
		@param validity_future: Future instance
		@returns: dictionary, including {pkgs, can_force}
		'''
		checkdirlist = kwargs.get('checkdirlist').get()
		checkdir = kwargs.get('checkdir')
		xpkg = kwargs.get('xpkg')
		fuse = kwargs.get('validity_future')
		can_force = kwargs.get('can_force')
		self.continue_ = False
		ebuildlist = []
		pkgs = {}
		for y in checkdirlist:
			file_is_ebuild = y.endswith(".ebuild")
			file_should_be_non_executable = (
				y in self.repo_settings.qadata.no_exec or file_is_ebuild)

			if file_should_be_non_executable:
				file_is_executable = stat.S_IMODE(
					os.stat(os.path.join(checkdir, y)).st_mode) & 0o111

				if file_is_executable:
					self.qatracker.add_error("file.executable", os.path.join(checkdir, y))
			if file_is_ebuild:
				pf = y[:-7]
				ebuildlist.append(pf)
				catdir = xpkg.split("/")[0]
				cpv = "%s/%s" % (catdir, pf)
				allvars = self.repo_settings.qadata.allvars
				try:
					myaux = dict(zip(allvars, self.portdb.aux_get(cpv, allvars)))
				except KeyError:
					fuse.set(False, ignore_InvalidState=True)
					self.qatracker.add_error("ebuild.syntax", os.path.join(xpkg, y))
					continue
				except IOError:
					fuse.set(False, ignore_InvalidState=True)
					self.qatracker.add_error("ebuild.output", os.path.join(xpkg, y))
					continue
				except InvalidPackageName:
					fuse.set(False, ignore_InvalidState=True)
					self.qatracker.add_error("ebuild.invalidname", os.path.join(xpkg, y))
					continue
				if not portage.eapi_is_supported(myaux["EAPI"]):
					fuse.set(False, ignore_InvalidState=True)
					self.qatracker.add_error("EAPI.unsupported", os.path.join(xpkg, y))
					continue
				pkgs[pf] = Package(
					cpv=cpv, metadata=myaux, root_config=self.root_config,
					type_name="ebuild")

		if len(pkgs) != len(ebuildlist):
			# If we can't access all the metadata then it's totally unsafe to
			# commit since there's no way to generate a correct Manifest.
			# Do not try to do any more QA checks on this package since missing
			# metadata leads to false positives for several checks, and false
			# positives confuse users.
			self.continue_ = True
			can_force.set(False, ignore_InvalidState=True)
		self.pkgs = pkgs
		# set our updated data
		dyn_pkgs = kwargs.get('pkgs')
		dyn_pkgs.set(pkgs)
		return self.continue_

	@property
	def runInPkgs(self):
		'''Package level scans'''
		return (True, [self.check_isebuild])

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check, self.set_pkg_data, self.bad_split_check, self.pkg_invalid])
