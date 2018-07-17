# Copyright 2012-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import re
import subprocess

from portage import os
from portage import _unicode_encode, _encodings
from portage.const import MANIFEST2_IDENTIFIERS
from portage.dep import _repo_separator
from portage.exception import InvalidDependString
from portage.localization import _
from portage.util import (atomic_ofstream, grablines,
	shlex_split, varexpand, writemsg)
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture
from portage.util._async.PipeLogger import PipeLogger
from portage.util._async.PopenProcess import PopenProcess
from _emerge.CompositeTask import CompositeTask
from _emerge.PipeReader import PipeReader
from .ManifestProcess import ManifestProcess

class ManifestTask(CompositeTask):

	__slots__ = ("cp", "distdir", "fetchlist_dict", "gpg_cmd",
		"gpg_vars", "repo_config", "force_sign_key", "_manifest_path")

	_PGP_HEADER = b"BEGIN PGP SIGNED MESSAGE"
	_manifest_line_re = re.compile(r'^(%s) ' % "|".join(MANIFEST2_IDENTIFIERS))
	_gpg_key_id_re = re.compile(r'^[0-9A-F]*$')
	_gpg_key_id_lengths = (8, 16, 24, 32, 40)

	def _start(self):
		self._manifest_path = os.path.join(self.repo_config.location,
			self.cp, "Manifest")

		self._start_task(
			AsyncTaskFuture(future=self.fetchlist_dict),
			self._start_with_fetchlist)

	def _start_with_fetchlist(self, fetchlist_task):
		if self._default_exit(fetchlist_task) != os.EX_OK:
			if not self.fetchlist_dict.cancelled():
				try:
					self.fetchlist_dict.result()
				except InvalidDependString as e:
					writemsg(
						_("!!! %s%s%s: SRC_URI: %s\n") %
						(self.cp, _repo_separator, self.repo_config.name, e),
						noiselevel=-1)
			self._async_wait()
			return
		self.fetchlist_dict = self.fetchlist_dict.result()
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
		null_fd = os.open('/dev/null', os.O_RDONLY)
		popen_proc = PopenProcess(proc=subprocess.Popen(
			["gpg", "--verify", self._manifest_path],
			stdin=null_fd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT),
			pipe_reader=PipeReader())
		os.close(null_fd)
		popen_proc.pipe_reader.input_files = {
			"producer" : popen_proc.proc.stdout}
		self._start_task(popen_proc, self._check_sig_key_exit)

	@staticmethod
	def _parse_gpg_key(output):
		"""
		Returns the first token which appears to represent a gpg key
		id, or None if there is no such token.
		"""
		regex = ManifestTask._gpg_key_id_re
		lengths = ManifestTask._gpg_key_id_lengths
		for token in output.split():
			m = regex.match(token)
			if m is not None and len(m.group(0)) in lengths:
				return m.group(0)
		return None

	@staticmethod
	def _normalize_gpg_key(key_str):
		"""
		Strips leading "0x" and trailing "!", and converts to uppercase
		(intended to be the same format as that in gpg --verify output).
		"""
		key_str = key_str.upper()
		if key_str.startswith("0X"):
			key_str = key_str[2:]
		key_str = key_str.rstrip("!")
		return key_str

	def _check_sig_key_exit(self, proc):
		self._assert_current(proc)

		parsed_key = self._parse_gpg_key(
			proc.pipe_reader.getvalue().decode('utf_8', 'replace'))
		if parsed_key is not None and \
			self._normalize_gpg_key(parsed_key) == \
			self._normalize_gpg_key(self.force_sign_key):
			self.returncode = os.EX_OK
			self._current_task = None
			self.wait()
			return

		if self._was_cancelled():
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
		gpg_proc = PopenProcess(proc=subprocess.Popen(gpg_cmd,
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
		# PipeLogger echos output and efficiently monitors for process
		# exit by listening for the stdout EOF event.
		gpg_proc.pipe_reader = PipeLogger(background=self.background,
			input_fd=gpg_proc.proc.stdout, scheduler=self.scheduler)
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

	def _need_signature(self):
		try:
			with open(_unicode_encode(self._manifest_path,
				encoding=_encodings['fs'], errors='strict'), 'rb') as f:
				return self._PGP_HEADER not in f.readline()
		except IOError as e:
			if e.errno in (errno.ENOENT, errno.ESTALE):
				return False
			raise
