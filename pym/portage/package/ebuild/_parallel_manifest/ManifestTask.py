# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import re
import subprocess

from portage import os
from portage import _unicode_encode, _encodings
from portage.const import MANIFEST2_IDENTIFIERS
from portage.util import (atomic_ofstream, grablines,
	shlex_split, varexpand, writemsg)
from portage.util._async.PopenProcess import PopenProcess
from _emerge.CompositeTask import CompositeTask
from _emerge.PipeReader import PipeReader
from _emerge.SpawnProcess import SpawnProcess
from .ManifestProcess import ManifestProcess

class ManifestTask(CompositeTask):

	__slots__ = ("cp", "distdir", "fetchlist_dict", "gpg_cmd",
		"gpg_vars", "repo_config", "force_sign_key", "_manifest_path",
		"_proc")

	_PGP_HEADER = b"BEGIN PGP SIGNED MESSAGE"
	_manifest_line_re = re.compile(r'^(%s) ' % "|".join(MANIFEST2_IDENTIFIERS))

	def _start(self):
		self._manifest_path = os.path.join(self.repo_config.location,
			self.cp, "Manifest")
		manifest_proc = ManifestProcess(cp=self.cp, distdir=self.distdir,
			fetchlist_dict=self.fetchlist_dict, repo_config=self.repo_config,
			scheduler=self.scheduler)
		self._start_task(manifest_proc, self._manifest_proc_exit)

	def _cancel(self):
		if self._proc is not None:
			self._proc.cancel()
		CompositeTask._cancel(self)

	def _proc_wait(self):
		if self._proc is not None:
			self._proc.wait()
			self._proc = None

	def _manifest_proc_exit(self, manifest_proc):
		self._assert_current(manifest_proc)
		if manifest_proc.returncode not in (os.EX_OK, manifest_proc.MODIFIED):
			self.returncode = manifest_proc.returncode
			self._current_task = None
			self.wait()
			return

		modified = manifest_proc.returncode == manifest_proc.MODIFIED
		sign = self.gpg_cmd is not None

		if not modified and sign:
			sign = self._need_signature()
			if not sign and self.force_sign_key is not None \
				and os.path.exists(self._manifest_path):
				self._check_sig_key()
				return

		if not sign or not os.path.exists(self._manifest_path):
			self.returncode = os.EX_OK
			self._current_task = None
			self.wait()
			return

		self._start_gpg_proc()

	def _check_sig_key(self):
		self._proc = PopenProcess(proc=subprocess.Popen(
			["gpg", "--verify", self._manifest_path],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
			scheduler=self.scheduler)
		pipe_reader = PipeReader(
			input_files={"producer" : self._proc.proc.stdout},
			scheduler=self.scheduler)
		self._start_task(pipe_reader, self._check_sig_key_exit)

	@staticmethod
	def _parse_gpg_key(output):
		"""
		Returns the last token of the first line, or None if there
		is no such token.
		"""
		output = output.splitlines()
		if output:
			output = output[0].split()
			if output:
				return output[-1]
		return None

	def _check_sig_key_exit(self, pipe_reader):
		self._assert_current(pipe_reader)

		parsed_key = self._parse_gpg_key(
			pipe_reader.getvalue().decode('utf_8', 'replace'))
		if parsed_key is not None and \
			parsed_key.lower() in self.force_sign_key.lower():
			self.returncode = os.EX_OK
			self._current_task = None
			self._proc_wait()
			self.wait()
			return

		self._strip_sig(self._manifest_path)
		self._start_gpg_proc()

	@staticmethod
	def _strip_sig(manifest_path):
		"""
		Strip an existing signature from a Manifest file.
		"""
		line_re = ManifestTask._manifest_line_re
		lines = grablines(manifest_path)
		f = None
		try:
			f = atomic_ofstream(manifest_path)
			for line in lines:
				if line_re.match(line) is not None:
					f.write(line)
			f.close()
			f = None
		finally:
			if f is not None:
				f.abort()

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
			self._proc_wait()
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
		self._proc_wait()
		self.wait()

	def _need_signature(self):
		try:
			with open(_unicode_encode(self._manifest_path,
				encoding=_encodings['fs'], errors='strict'), 'rb') as f:
				return self._PGP_HEADER not in f.readline()
		except IOError as e:
			if e.errno in (errno.ENOENT, errno.ESTALE):
				return False
			raise
