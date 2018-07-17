# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.elog.messages import eerror
from portage.util.SlotObject import SlotObject

class EbuildFetchonly(SlotObject):

	__slots__ = ("fetch_all", "pkg", "pretend", "settings")

	def execute(self):
		settings = self.settings
		pkg = self.pkg
		portdb = pkg.root_config.trees["porttree"].dbapi
		ebuild_path = portdb.findname(pkg.cpv, myrepo=pkg.repo)
		if ebuild_path is None:
			raise AssertionError("ebuild not found for '%s'" % pkg.cpv)
		settings.setcpv(pkg)
		debug = settings.get("PORTAGE_DEBUG") == "1"

		rval = portage.doebuild(ebuild_path, "fetch",
			settings=settings, debug=debug,
			listonly=self.pretend, fetchonly=1, fetchall=self.fetch_all,
			mydbapi=portdb, tree="porttree")

		# For pretend mode, this error message is suppressed,
		# and the unsuccessful return value is used to trigger
		# a call to the pkg_nofetch phase.
		if rval != os.EX_OK and not self.pretend:
			msg = "Fetch failed for '%s'" % (pkg.cpv,)
			eerror(msg, phase="unpack", key=pkg.cpv)

		return rval
