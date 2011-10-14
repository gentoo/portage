# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SubProcess import SubProcess
from _emerge.PollConstants import PollConstants
import sys
from portage.cache.mappings import slot_dict_class
import portage
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
import fcntl
import io

class EbuildMetadataPhase(SubProcess):

	"""
	Asynchronous interface for the ebuild "depend" phase which is
	used to extract metadata from the ebuild.
	"""

	__slots__ = ("cpv", "ebuild_hash", "fd_pipes", "metadata_callback",
		"metadata", "portdb", "repo_path", "settings") + \
		("_raw_metadata",)

	_file_names = ("ebuild",)
	_files_dict = slot_dict_class(_file_names, prefix="")
	_metadata_fd = 9

	def _start(self):
		settings = self.settings
		settings.setcpv(self.cpv)
		ebuild_path = self.ebuild_hash.location

		eapi = None
		if eapi is None and \
			'parse-eapi-ebuild-head' in settings.features:
			eapi = portage._parse_eapi_ebuild_head(
				io.open(_unicode_encode(ebuild_path,
				encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'],
				errors='replace'))

		if eapi is not None:
			if not portage.eapi_is_supported(eapi):
				self.metadata_callback(self.cpv, ebuild_path,
					self.repo_path, {'EAPI' : eapi}, self.ebuild_hash.mtime)
				self._set_returncode((self.pid, os.EX_OK << 8))
				self.wait()
				return

			settings.configdict['pkg']['EAPI'] = eapi

		debug = settings.get("PORTAGE_DEBUG") == "1"
		master_fd = None
		slave_fd = None
		fd_pipes = None
		if self.fd_pipes is not None:
			fd_pipes = self.fd_pipes.copy()
		else:
			fd_pipes = {}

		fd_pipes.setdefault(0, sys.stdin.fileno())
		fd_pipes.setdefault(1, sys.stdout.fileno())
		fd_pipes.setdefault(2, sys.stderr.fileno())

		# flush any pending output
		for fd in fd_pipes.values():
			if fd == sys.stdout.fileno():
				sys.stdout.flush()
			if fd == sys.stderr.fileno():
				sys.stderr.flush()

		fd_pipes_orig = fd_pipes.copy()
		self._files = self._files_dict()
		files = self._files

		master_fd, slave_fd = os.pipe()
		fcntl.fcntl(master_fd, fcntl.F_SETFL,
			fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		fd_pipes[self._metadata_fd] = slave_fd

		self._raw_metadata = []
		files.ebuild = os.fdopen(master_fd, 'rb', 0)
		self._reg_id = self.scheduler.register(files.ebuild.fileno(),
			self._registered_events, self._output_handler)
		self._registered = True

		retval = portage.doebuild(ebuild_path, "depend",
			settings["ROOT"], settings, debug,
			mydbapi=self.portdb, tree="porttree",
			fd_pipes=fd_pipes, returnpid=True)

		os.close(slave_fd)

		if isinstance(retval, int):
			# doebuild failed before spawning
			self._unregister()
			self._set_returncode((self.pid, retval << 8))
			self.wait()
			return

		self.pid = retval[0]
		portage.process.spawned_pids.remove(self.pid)

	def _output_handler(self, fd, event):

		if event & PollConstants.POLLIN:
			self._raw_metadata.append(self._files.ebuild.read())
			if not self._raw_metadata[-1]:
				self._unregister()
				self.wait()

		self._unregister_if_appropriate(event)

	def _set_returncode(self, wait_retval):
		SubProcess._set_returncode(self, wait_retval)
		if self.returncode == os.EX_OK:
			metadata_lines = ''.join(_unicode_decode(chunk,
				encoding=_encodings['repo.content'], errors='replace')
				for chunk in self._raw_metadata).splitlines()
			if len(portage.auxdbkeys) != len(metadata_lines):
				# Don't trust bash's returncode if the
				# number of lines is incorrect.
				self.returncode = 1
			else:
				metadata = zip(portage.auxdbkeys, metadata_lines)
				self.metadata = self.metadata_callback(self.cpv,
					self.repo_path, metadata, self.ebuild_hash)

