# -*- coding:utf-8 -*-

import stat

from _emerge.Package import Package
from _emerge.RootConfig import RootConfig

# import our initialized portage instance
from repoman._portage import portage

from portage import os

from repoman.qa_data import no_exec, allvars


class IsEbuild(object):

	def __init__(self, repoman_settings, repo_settings, portdb, qatracker):
		''''''
		self.portdb = portdb
		self.qatracker = qatracker
		self.root_config = RootConfig(
			repoman_settings, repo_settings.trees[repo_settings.root], None)

	def check(self, checkdirlist, checkdir, xpkg):
		self.continue_ = False
		ebuildlist = []
		pkgs = {}
		allvalid = True
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
					allvalid = False
					self.qatracker.add_error("ebuild.syntax", os.path.join(xpkg, y))
					continue
				except IOError:
					allvalid = False
					self.qatracker.add_error("ebuild.output", os.path.join(xpkg, y))
					continue
				if not portage.eapi_is_supported(myaux["EAPI"]):
					allvalid = False
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

		return pkgs, allvalid
