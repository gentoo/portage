# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import codecs
import logging
import portage
from portage import os
from _emerge.AsynchronousTask import AsynchronousTask
from _emerge.unmerge import unmerge
from _emerge.UninstallFailure import UninstallFailure

class PackageUninstall(AsynchronousTask):

	__slots__ = ("ldpath_mtimes", "opts", "pkg", "scheduler", "settings")

	def _start(self):
		try:
			unmerge(self.pkg.root_config, self.opts, "unmerge",
				[self.pkg.cpv], self.ldpath_mtimes, clean_world=0,
				clean_delay=0, raise_on_error=1, scheduler=self.scheduler,
				writemsg_level=self._writemsg_level)
		except UninstallFailure, e:
			self.returncode = e.status
		else:
			self.returncode = os.EX_OK
		self.wait()

	def _writemsg_level(self, msg, level=0, noiselevel=0):

		log_path = self.settings.get("PORTAGE_LOG_FILE")
		background = self.background

		if log_path is None:
			if not (background and level < logging.WARNING):
				portage.util.writemsg_level(msg,
					level=level, noiselevel=noiselevel)
		else:
			if not background:
				portage.util.writemsg_level(msg,
					level=level, noiselevel=noiselevel)

			f = codecs.open(log_path, mode='a',
				encoding='utf_8', errors='replace')
			try:
				f.write(msg)
			finally:
				f.close()

