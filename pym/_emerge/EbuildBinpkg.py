# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.MiscFunctionsProcess import MiscFunctionsProcess
from portage import os
from portage.exception import PermissionDenied
from portage.package.ebuild.doebuild import _spawn_actionmap
from portage.package.ebuild.doebuild import spawn as doebuild_spawn
from portage.util import ensure_dirs

class EbuildBinpkg(MiscFunctionsProcess):
	"""
	This assumes that src_install() has successfully completed.
	"""
	__slots__ = ("_binpkg_tmpfile",)

	def __init__(self, **kwargs):
		MiscFunctionsProcess.__init__(self, phase="package", **kwargs)

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
		self.logfile = self.settings.get("PORTAGE_LOG_FILE")
		self.commands = ["dyn_" + self.phase]
		MiscFunctionsProcess._start(self)

	def _spawn(self, args, **kwargs):
		self.settings["EBUILD_PHASE"] = self.phase
		self.settings["PORTAGE_BINPKG_TMPFILE"] = self._binpkg_tmpfile
		kwargs.update(_spawn_actionmap(self.settings)[self.phase]["args"])
		try:
			return doebuild_spawn(" ".join(args), self.settings, **kwargs)
		finally:
			self.settings.pop("EBUILD_PHASE", None)
			self.settings.pop("PORTAGE_BINPKG_TMPFILE", None)

	def _set_returncode(self, wait_retval):
		MiscFunctionsProcess._set_returncode(self, wait_retval)
		if self.returncode == os.EX_OK:
			pkg = self.pkg
			bintree = pkg.root_config.trees["bintree"]
			bintree.inject(pkg.cpv, filename=self._binpkg_tmpfile)
