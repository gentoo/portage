# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.util import shlex_split, varexpand, writemsg
from _emerge.CompositeTask import CompositeTask
from _emerge.SpawnProcess import SpawnProcess
from .ManifestProcess import ManifestProcess

class ManifestTask(CompositeTask):

	__slots__ = ("cp", "distdir", "fetchlist_dict", "gpg_cmd",
		"gpg_vars", "repo_config", "_manifest_path")

	def _start(self):
		self._manifest_path = os.path.join(self.repo_config.location,
			self.cp, "Manifest")
		manifest_proc = ManifestProcess(cp=self.cp, distdir=self.distdir,
			fetchlist_dict=self.fetchlist_dict, repo_config=self.repo_config,
			scheduler=self.scheduler)
		self._start_task(manifest_proc, self._manifest_proc_exit)

	def _manifest_proc_exit(self, manifest_proc):
		self._assert_current(manifest_proc)
		if manifest_proc.returncode not in (os.EX_OK, manifest_proc.MODIFIED):
			self.returncode = manifest_proc.returncode
			self._current_task = None
			self.wait()
			return

		modified = manifest_proc.returncode == manifest_proc.MODIFIED

		if self.gpg_cmd is None or not modified or \
			not os.path.exists(self._manifest_path):
			self.returncode = os.EX_OK
			self._current_task = None
			self.wait()
			return

		self._start_gpg_proc()

	def _start_gpg_proc(self):
		gpg_vars = self.gpg_vars
		if gpg_vars is None:
			gpg_vars = {}
		else:
			gpg_vars = gpg_vars.copy()
		gpg_vars["FILE"] = self._manifest_path
		gpg_cmd = varexpand(self.gpg_cmd, mydict=gpg_vars)
		gpg_cmd = shlex_split(gpg_cmd)
		gpg_proc = SpawnProcess(
			args=gpg_cmd, env=os.environ, scheduler=self.scheduler)
		self._start_task(gpg_proc, self._gpg_proc_exit)

	def _gpg_proc_exit(self, gpg_proc):
		if self._default_exit(gpg_proc) != os.EX_OK:
			self.wait()
			return

		rename_args = (self._manifest_path + ".asc", self._manifest_path)
		try:
			os.rename(*rename_args)
		except OSError as e:
			writemsg("!!! rename('%s', '%s'): %s\n" % rename_args + (e,),
				noiselevel=-1)
			try:
				os.unlink(self._manifest_path + ".asc")
			except OSError:
				pass
			self.returncode = 1
		else:
			self.returncode = os.EX_OK

		self._current_task = None
		self.wait()
