# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SlotObject import SlotObject
import shutil
import portage
from portage import os
from portage.elog.messages import eerror

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

		if 'fetch' in pkg.metadata.restrict:
			rval = self._execute_with_builddir()
		else:
			rval = portage.doebuild(ebuild_path, "fetch",
				settings["ROOT"], settings, debug=debug,
				listonly=self.pretend, fetchonly=1, fetchall=self.fetch_all,
				mydbapi=portdb, tree="porttree")

			if rval != os.EX_OK:
				msg = "Fetch failed for '%s'" % (pkg.cpv,)
				eerror(msg, phase="unpack", key=pkg.cpv)

		return rval

	def _execute_with_builddir(self):
		# To spawn pkg_nofetch requires PORTAGE_BUILDDIR for
		# ensuring sane $PWD (bug #239560) and storing elog
		# messages. Use a private temp directory, in order
		# to avoid locking the main one.
		settings = self.settings
		global_tmpdir = settings["PORTAGE_TMPDIR"]
		from tempfile import mkdtemp
		try:
			private_tmpdir = mkdtemp("", "._portage_fetch_.", global_tmpdir)
		except OSError as e:
			if e.errno != portage.exception.PermissionDenied.errno:
				raise
			raise portage.exception.PermissionDenied(global_tmpdir)
		settings["PORTAGE_TMPDIR"] = private_tmpdir
		settings.backup_changes("PORTAGE_TMPDIR")
		try:
			retval = self._execute()
		finally:
			settings["PORTAGE_TMPDIR"] = global_tmpdir
			settings.backup_changes("PORTAGE_TMPDIR")
			shutil.rmtree(private_tmpdir)
		return retval

	def _execute(self):
		settings = self.settings
		pkg = self.pkg
		root_config = pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		ebuild_path = portdb.findname(pkg.cpv, myrepo=pkg.repo)
		if ebuild_path is None:
			raise AssertionError("ebuild not found for '%s'" % pkg.cpv)
		debug = settings.get("PORTAGE_DEBUG") == "1"
		retval = portage.doebuild(ebuild_path, "fetch",
			self.settings["ROOT"], self.settings, debug=debug,
			listonly=self.pretend, fetchonly=1, fetchall=self.fetch_all,
			mydbapi=portdb, tree="porttree")

		if retval != os.EX_OK:
			msg = "Fetch failed for '%s'" % (pkg.cpv,)
			eerror(msg, phase="unpack", key=pkg.cpv)

		portage.elog.elog_process(self.pkg.cpv, self.settings)
		return retval

