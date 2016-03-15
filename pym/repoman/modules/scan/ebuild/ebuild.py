# -*- coding:utf-8 -*-

from __future__ import print_function, unicode_literals

import re

from repoman.modules.scan.scanbase import ScanBase
# import our initialized portage instance
from repoman._portage import portage
from portage import os

pv_toolong_re = re.compile(r'[0-9]{19,}')


class Ebuild(ScanBase):
	'''Class to run primary checks on ebuilds'''

	def __init__(self, **kwargs):
		'''Class init

		@param qatracker: QATracker instance
		@param repo_settings: repository settings instance
		@param vcs_settings: VCSSettings instance
		@param changed: changes dictionary
		@param checks: checks dictionary
		'''
		super(Ebuild, self).__init__(**kwargs)
		self.qatracker = kwargs.get('qatracker')
		self.repo_settings = kwargs.get('repo_settings')
		self.vcs_settings = kwargs.get('vcs_settings')
		self.checks = kwargs.get('checks')
		self.changed = None
		self.xpkg = None
		self.y_ebuild = None
		self.pkg = None
		self.metadata = None
		self.eapi = None
		self.inherited = None
		self.keywords = None

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
		return {'continue': False, 'ebuild': self}

	def set_pkg_data(self, **kwargs):
		'''Sets some classwide data needed for some of the checks

		@param pkgs: the dynamic list of ebuilds
		@returns: dictionary
		'''
		self.pkg = kwargs.get('pkgs')[self.y_ebuild]
		self.metadata = self.pkg._metadata
		self.eapi = self.metadata["EAPI"]
		self.inherited = self.pkg.inherited
		self.keywords = self.metadata["KEYWORDS"].split()
		self.archs = set(kw.lstrip("~") for kw in self.keywords if not kw.startswith("-"))
		return {'continue': False}

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
				return {'continue': True}
		elif myesplit[0] != pkgdir:
			print(pkgdir, myesplit[0])
			self.qatracker.add_error(
				"ebuild.namenomatch", self.xpkg + "/" + self.y_ebuild + ".ebuild")
			return {'continue': True}
		return {'continue': False}

	def pkg_invalid(self, **kwargs):
		'''Sets some pkg info and checks for invalid packages

		@param validity_fuse: Fuse instance
		@returns: dictionary, including {pkg object}
		'''
		fuse = kwargs.get('validity_fuse')
		if self.pkg.invalid:
			for k, msgs in self.pkg.invalid.items():
				for msg in msgs:
					self.qatracker.add_error(k, "%s: %s" % (self.relative_path, msg))
			fuse.pop()
			return {'continue': True, 'pkg': self.pkg}
		return {'continue': False, 'pkg': self.pkg}

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check, self.set_pkg_data, self.bad_split_check, self.pkg_invalid])
