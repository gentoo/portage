# Copyright 1999-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import io
import sys

from _emerge.CompositeTask import CompositeTask
import portage
from portage import os
from portage.checksum import (_apply_hash_filter,
	_filter_unaccelarated_hashes, _hash_filter)
from portage.output import EOutput
from portage.util._async.FileDigester import FileDigester
from portage.package.ebuild.fetch import _checksum_failure_temp_file

class BinpkgVerifier(CompositeTask):
	__slots__ = ("logfile", "pkg", "_digests", "_pkg_path")

	def _start(self):

		bintree = self.pkg.root_config.trees["bintree"]
		digests = bintree._get_digests(self.pkg)
		if "size" not in digests:
			self.returncode = os.EX_OK
			self._async_wait()
			return

		digests = _filter_unaccelarated_hashes(digests)
		hash_filter = _hash_filter(
			bintree.settings.get("PORTAGE_CHECKSUM_FILTER", ""))
		if not hash_filter.transparent:
			digests = _apply_hash_filter(digests, hash_filter)

		self._digests = digests

		try:
			size = os.stat(self._pkg_path).st_size
		except OSError as e:
			if e.errno not in (errno.ENOENT, errno.ESTALE):
				raise
			self.scheduler.output(("!!! Fetching Binary failed "
				"for '%s'\n") % self.pkg.cpv, log_path=self.logfile,
				background=self.background)
			self.returncode = 1
			self._async_wait()
			return
		else:
			if size != digests["size"]:
				self._digest_exception("size", size, digests["size"])
				self.returncode = 1
				self._async_wait()
				return

		self._start_task(FileDigester(file_path=self._pkg_path,
			hash_names=(k for k in digests if k != "size"),
			background=self.background, logfile=self.logfile,
			scheduler=self.scheduler),
			self._digester_exit)

	def _digester_exit(self, digester):

		if self._default_exit(digester) != os.EX_OK:
			self.wait()
			return

		for hash_name in digester.hash_names:
			if digester.digests[hash_name] != self._digests[hash_name]:
				self._digest_exception(hash_name,
					digester.digests[hash_name], self._digests[hash_name])
				self.returncode = 1
				self.wait()
				return

		if self.pkg.root_config.settings.get("PORTAGE_QUIET") != "1":
			self._display_success()

		self.returncode = os.EX_OK
		self.wait()

	def _display_success(self):
		stdout_orig = sys.stdout
		stderr_orig = sys.stderr
		global_havecolor = portage.output.havecolor
		out = io.StringIO()
		try:
			sys.stdout = out
			sys.stderr = out
			if portage.output.havecolor:
				portage.output.havecolor = not self.background

			path = self._pkg_path
			if path.endswith(".partial"):
				path = path[:-len(".partial")]
			eout = EOutput()
			eout.ebegin("%s %s ;-)" % (os.path.basename(path),
				" ".join(sorted(self._digests))))
			eout.eend(0)

		finally:
			sys.stdout = stdout_orig
			sys.stderr = stderr_orig
			portage.output.havecolor = global_havecolor

		self.scheduler.output(out.getvalue(), log_path=self.logfile,
			background=self.background)

	def _digest_exception(self, name, value, expected):

		head, tail = os.path.split(self._pkg_path)
		temp_filename = _checksum_failure_temp_file(self.pkg.root_config.settings, head, tail)

		self.scheduler.output((
			"\n!!! Digest verification failed:\n"
			"!!! %s\n"
			"!!! Reason: Failed on %s verification\n"
			"!!! Got: %s\n"
			"!!! Expected: %s\n"
			"File renamed to '%s'\n") %
			(self._pkg_path, name, value, expected, temp_filename),
			log_path=self.logfile,
			background=self.background)
