# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.checksum import perform_multiple_checksums
from portage.util._async.ForkProcess import ForkProcess
from _emerge.PipeReader import PipeReader

class FileDigester(ForkProcess):
	"""
	Asynchronously generate file digests. Pass in file_path and
	hash_names, and after successful execution, the digests
	attribute will be a dict containing all of the requested
	digests.
	"""

	__slots__ = ('file_path', 'digests', 'hash_names',
		'_digest_pipe_reader', '_digest_pw')

	def _start(self):
		pr, pw = os.pipe()
		self.fd_pipes = {}
		self.fd_pipes[pw] = pw
		self._digest_pw = pw
		self._digest_pipe_reader = PipeReader(
			input_files={"input":pr},
			scheduler=self.scheduler)
		self._digest_pipe_reader.addExitListener(self._digest_pipe_reader_exit)
		self._digest_pipe_reader.start()
		ForkProcess._start(self)
		os.close(pw)

	def _run(self):
		digests = perform_multiple_checksums(self.file_path,
			hashes=self.hash_names)

		buf = "".join("%s=%s\n" % item
			for item in digests.items()).encode('utf_8')

		while buf:
			buf = buf[os.write(self._digest_pw, buf):]

		return os.EX_OK

	def _parse_digests(self, data):

		digests = {}
		for line in data.decode('utf_8').splitlines():
			parts = line.split('=', 1)
			if len(parts) == 2:
				digests[parts[0]] = parts[1]

		self.digests = digests

	def _async_waitpid(self):
		# Ignore this event, since we want to ensure that we
		# exit only after _digest_pipe_reader has reached EOF.
		if self._digest_pipe_reader is None:
			ForkProcess._async_waitpid(self)

	def _digest_pipe_reader_exit(self, pipe_reader):
		self._parse_digests(pipe_reader.getvalue())
		self._digest_pipe_reader = None
		if self.pid is None:
			self._unregister()
			self._async_wait()
		else:
			self._async_waitpid()

	def _unregister(self):
		ForkProcess._unregister(self)

		pipe_reader = self._digest_pipe_reader
		if pipe_reader is not None:
			self._digest_pipe_reader = None
			pipe_reader.removeExitListener(self._digest_pipe_reader_exit)
			pipe_reader.cancel()
