# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.EbuildProcess import EbuildProcess
from portage import os

class EbuildBinpkg(EbuildProcess):
	"""
	This assumes that src_install() has successfully completed.
	"""
	__slots__ = ("_binpkg_tmpfile",)

	def _start(self):
		self.phase = "package"
		self.tree = "porttree"
		pkg = self.pkg
		root_config = pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		bintree = root_config.trees["bintree"]
		ebuild_path = portdb.findname(pkg.cpv)
		if ebuild_path is None:
			raise AssertionError("ebuild not found for '%s'" % pkg.cpv)
		settings = self.settings
		debug = settings.get("PORTAGE_DEBUG") == "1"

		bintree.prevent_collision(pkg.cpv)
		binpkg_tmpfile = os.path.join(bintree.pkgdir,
			pkg.cpv + ".tbz2." + str(os.getpid()))
		self._binpkg_tmpfile = binpkg_tmpfile
		settings["PORTAGE_BINPKG_TMPFILE"] = binpkg_tmpfile
		settings.backup_changes("PORTAGE_BINPKG_TMPFILE")

		try:
			EbuildProcess._start(self)
		finally:
			settings.pop("PORTAGE_BINPKG_TMPFILE", None)

	def _set_returncode(self, wait_retval):
		EbuildProcess._set_returncode(self, wait_retval)

		pkg = self.pkg
		bintree = pkg.root_config.trees["bintree"]
		binpkg_tmpfile = self._binpkg_tmpfile
		if self.returncode == os.EX_OK:
			bintree.inject(pkg.cpv, filename=binpkg_tmpfile)

