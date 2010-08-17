# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.EbuildProcess import EbuildProcess
from portage import os
from portage.exception import PermissionDenied
from portage.util import ensure_dirs

class EbuildBinpkg(EbuildProcess):
	"""
	This assumes that src_install() has successfully completed.
	"""
	__slots__ = ("_binpkg_tmpfile", "pkg")

	def __init__(self, **kwargs):
		EbuildProcess.__init__(self, phase="package", **kwargs)

	def _start(self):
		pkg = self.pkg
		root_config = pkg.root_config
		bintree = root_config.trees["bintree"]
		bintree.prevent_collision(pkg.cpv)
		binpkg_tmpfile = os.path.join(bintree.pkgdir,
			pkg.cpv + ".tbz2." + str(os.getpid()))
		parent_dir = os.path.dirname(binpkg_tmpfile)
		ensure_dirs(parent_dir)
		if not os.access(parent_dir, os.W_OK):
			raise PermissionDenied(
				"access('%s', os.W_OK)" % parent_dir)

		self._binpkg_tmpfile = binpkg_tmpfile
		self.settings["PORTAGE_BINPKG_TMPFILE"] = self._binpkg_tmpfile
		EbuildProcess._start(self)

	def _set_returncode(self, wait_retval):
		EbuildProcess._set_returncode(self, wait_retval)
		self.settings.pop("PORTAGE_BINPKG_TMPFILE", None)
		if self.returncode == os.EX_OK:
			pkg = self.pkg
			bintree = pkg.root_config.trees["bintree"]
			bintree.inject(pkg.cpv, filename=self._binpkg_tmpfile)
