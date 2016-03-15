# -*- coding:utf-8 -*-

import stat

from _emerge.Package import Package
from _emerge.RootConfig import RootConfig

# import our initialized portage instance
from repoman._portage import portage

from portage import os

from repoman.qa_data import no_exec, allvars
from repoman.modules.scan.scanbase import ScanBase

class IsEbuild(ScanBase):
	'''Performs basic tests to confirm it is an ebuild'''

	def __init__(self, **kwargs):
		'''
		@param portdb: portdb instance
		@param qatracker: QATracker instance
		@param repo_settings: repository settings instance
		'''
		super(IsEbuild, self).__init__(**kwargs)
		self.portdb = kwargs.get('portdb')
		self.qatracker = kwargs.get('qatracker')
		repo_settings = kwargs.get('repo_settings')
		self.root_config = RootConfig(repo_settings.repoman_settings,
			repo_settings.trees[repo_settings.root], None)

	def check(self, **kwargs):
		'''Test the file for qualifications that is is an ebuild

		@param checkdirlist: list of files in the current package directory
		@param checkdir: current package directory path
		@param xpkg: current package directory being checked
		@param validity_fuse: Fuse instance
		@returns: dictionary, including {pkgs, can_force}
		'''
		checkdirlist = kwargs.get('checkdirlist')
		checkdir = kwargs.get('checkdir')
		xpkg = kwargs.get('xpkg')
		fuse = kwargs.get('validity_fuse')
		self.continue_ = False
		ebuildlist = []
		pkgs = {}
		for y in checkdirlist:
			file_is_ebuild = y.endswith(".ebuild")
			file_should_be_non_executable = y in no_exec or file_is_ebuild

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
				try:
					myaux = dict(zip(allvars, self.portdb.aux_get(cpv, allvars)))
				except KeyError:
					fuse.pop()
					self.qatracker.add_error("ebuild.syntax", os.path.join(xpkg, y))
					continue
				except IOError:
					fuse.pop()
					self.qatracker.add_error("ebuild.output", os.path.join(xpkg, y))
					continue
				if not portage.eapi_is_supported(myaux["EAPI"]):
					fuse.pop()
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

		return {'continue': self.continue_, 'pkgs': pkgs,
			'can_force': not self.continue_}

	@property
	def runInPkgs(self):
		'''Package level scans'''
		return (True, [self.check])
