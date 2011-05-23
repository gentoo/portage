# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import portage
from portage import os
from _emerge.emergelog import emergelog
from _emerge.CompositeTask import CompositeTask
from _emerge.unmerge import _unmerge_display

class PackageUninstall(CompositeTask):

	__slots__ = ("world_atom", "ldpath_mtimes", "opts",
			"pkg", "settings")

	def _start(self):

		retval, pkgmap = _unmerge_display(self.pkg.root_config,
			self.opts, "unmerge", [self.pkg.cpv], clean_delay=0,
			writemsg_level=self._writemsg_level)

		if retval != os.EX_OK:
			self.returncode = retval
			self.wait()
			return

		self._writemsg_level(">>> Unmerging %s...\n" % (self.pkg.cpv,),
			noiselevel=-1)
		self._emergelog("=== Unmerging... (%s)" % (self.pkg.cpv,))

		cat, pf = portage.catsplit(self.pkg.cpv)
		retval = portage.unmerge(cat, pf, settings=self.settings,
			vartree=self.pkg.root_config.trees["vartree"],
			ldpath_mtimes=self.ldpath_mtimes,
			scheduler=self.scheduler)

		if retval != os.EX_OK:
			self._emergelog(" !!! unmerge FAILURE: %s" % (self.pkg.cpv,))
		else:
			self._emergelog(" >>> unmerge success: %s" % (self.pkg.cpv,))
			self.world_atom(self.pkg)

		self.returncode = retval
		self.wait()

	def _emergelog(self, msg):
		emergelog("notitles" not in self.settings.features, msg)

	def _writemsg_level(self, msg, level=0, noiselevel=0):

		log_path = self.settings.get("PORTAGE_LOG_FILE")
		background = self.background

		if log_path is None:
			if not (background and level < logging.WARNING):
				portage.util.writemsg_level(msg,
					level=level, noiselevel=noiselevel)
		else:
			self.scheduler.output(msg, level=level, noiselevel=noiselevel)
