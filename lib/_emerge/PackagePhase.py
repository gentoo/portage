# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io

from _emerge.CompositeTask import CompositeTask
from _emerge.EbuildProcess import EbuildProcess
from _emerge.SpawnProcess import SpawnProcess

import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.util._async.AsyncFunction import AsyncFunction
from portage.util.install_mask import install_mask_dir, InstallMask


class PackagePhase(CompositeTask):
	"""
	Invokes the package phase and handles PKG_INSTALL_MASK.
	"""

	__slots__ = ("actionmap", "fd_pipes", "logfile", "settings",
		"_pkg_install_mask", "_proot")

	_shell_binary = portage.const.BASH_BINARY

	def _start(self):
		try:
			with io.open(_unicode_encode(
				os.path.join(self.settings["PORTAGE_BUILDDIR"],
				"build-info", "PKG_INSTALL_MASK"),
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace') as f:
				self._pkg_install_mask = InstallMask(f.read())
		except EnvironmentError:
			self._pkg_install_mask = None
		if self._pkg_install_mask:
			self._proot = os.path.join(self.settings['T'], 'packaging')
			self._start_task(SpawnProcess(
				args=[self._shell_binary, '-e', '-c', ('rm -rf {PROOT}; '
				'cp -pPR $(cp --help | grep -q -- "^[[:space:]]*-l," && echo -l)'
				' "${{D}}" {PROOT}').format(PROOT=portage._shell_quote(self._proot))],
				background=self.background, env=self.settings.environ(),
				scheduler=self.scheduler, logfile=self.logfile),
				self._copy_proot_exit)
		else:
			self._proot = self.settings['D']
			self._start_package_phase()

	def _copy_proot_exit(self, proc):
		if self._default_exit(proc) != os.EX_OK:
			self.wait()
		else:
			self._start_task(AsyncFunction(
				target=install_mask_dir,
				args=(os.path.join(self._proot,
					self.settings['EPREFIX'].lstrip(os.sep)),
					self._pkg_install_mask)),
				self._pkg_install_mask_exit)

	def _pkg_install_mask_exit(self, proc):
		if self._default_exit(proc) != os.EX_OK:
			self.wait()
		else:
			self._start_package_phase()

	def _start_package_phase(self):
		ebuild_process = EbuildProcess(actionmap=self.actionmap,
			background=self.background, fd_pipes=self.fd_pipes,
			logfile=self.logfile, phase="package",
			scheduler=self.scheduler, settings=self.settings)

		if self._pkg_install_mask:
			d_orig = self.settings["D"]
			try:
				self.settings["D"] = self._proot
				self._start_task(ebuild_process, self._pkg_install_mask_cleanup)
			finally:
				self.settings["D"] = d_orig
		else:
			self._start_task(ebuild_process, self._default_final_exit)

	def _pkg_install_mask_cleanup(self, proc):
		if self._default_exit(proc) != os.EX_OK:
			self.wait()
		else:
			self._start_task(SpawnProcess(
				args=['rm', '-rf', self._proot],
				background=self.background, env=self.settings.environ(),
				scheduler=self.scheduler, logfile=self.logfile),
				self._default_final_exit)
