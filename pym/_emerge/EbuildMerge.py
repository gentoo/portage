# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SlotObject import SlotObject
import portage
from portage import os

class EbuildMerge(SlotObject):

	__slots__ = ("find_blockers", "logger", "ldpath_mtimes",
		"pkg", "pkg_count", "pkg_path", "pretend",
		"scheduler", "settings", "tree", "world_atom")

	def execute(self):
		root_config = self.pkg.root_config
		settings = self.settings
		retval = portage.merge(settings["CATEGORY"],
			settings["PF"], settings["D"],
			os.path.join(settings["PORTAGE_BUILDDIR"],
			"build-info"), root_config.root, settings,
			myebuild=settings["EBUILD"],
			mytree=self.tree, mydbapi=root_config.trees[self.tree].dbapi,
			vartree=root_config.trees["vartree"],
			prev_mtimes=self.ldpath_mtimes,
			scheduler=self.scheduler,
			blockers=self.find_blockers)

		if retval == os.EX_OK:
			self.world_atom(self.pkg)
			self._log_success()

		return retval

	def _log_success(self):
		pkg = self.pkg
		pkg_count = self.pkg_count
		pkg_path = self.pkg_path
		logger = self.logger
		if "noclean" not in self.settings.features:
			short_msg = "emerge: (%s of %s) %s Clean Post" % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv)
			logger.log((" === (%s of %s) " + \
				"Post-Build Cleaning (%s::%s)") % \
				(pkg_count.curval, pkg_count.maxval, pkg.cpv, pkg_path),
				short_msg=short_msg)
		logger.log(" ::: completed emerge (%s of %s) %s to %s" % \
			(pkg_count.curval, pkg_count.maxval, pkg.cpv, pkg.root))

