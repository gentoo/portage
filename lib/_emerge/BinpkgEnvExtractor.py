# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno

from _emerge.CompositeTask import CompositeTask
from _emerge.SpawnProcess import SpawnProcess
from portage import os, _shell_quote, _unicode_encode
from portage.const import BASH_BINARY

class BinpkgEnvExtractor(CompositeTask):
	"""
	Extract environment.bz2 for a binary or installed package.
	"""
	__slots__ = ('settings',)

	def saved_env_exists(self):
		return os.path.exists(self._get_saved_env_path())

	def dest_env_exists(self):
		return os.path.exists(self._get_dest_env_path())

	def _get_saved_env_path(self):
		return os.path.join(os.path.dirname(self.settings['EBUILD']),
			"environment.bz2")

	def _get_dest_env_path(self):
		return os.path.join(self.settings["T"], "environment")

	def _start(self):
		saved_env_path = self._get_saved_env_path()
		dest_env_path = self._get_dest_env_path()
		shell_cmd = "${PORTAGE_BUNZIP2_COMMAND:-${PORTAGE_BZIP2_COMMAND} -d} -c -- %s > %s" % \
			(_shell_quote(saved_env_path),
			_shell_quote(dest_env_path))

		logfile = None
		if self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
			logfile = self.settings.get("PORTAGE_LOG_FILE")

		extractor_proc = SpawnProcess(
			args=[BASH_BINARY, "-c", shell_cmd],
			background=self.background,
			env=self.settings.environ(),
			scheduler=self.scheduler,
			logfile=logfile)

		self._start_task(extractor_proc, self._extractor_exit)

	def _remove_dest_env(self):
		try:
			os.unlink(self._get_dest_env_path())
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise

	def _extractor_exit(self, extractor_proc):

		if self._default_exit(extractor_proc) != os.EX_OK:
			self._remove_dest_env()
			self.wait()
			return

		# This is a signal to ebuild.sh, so that it knows to filter
		# out things like SANDBOX_{DENY,PREDICT,READ,WRITE} that
		# would be preserved between normal phases.
		open(_unicode_encode(self._get_dest_env_path() + '.raw'), 'wb').close()

		self._current_task = None
		self.returncode = os.EX_OK
		self.wait()
