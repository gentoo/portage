# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SubProcess import SubProcess
import sys
from portage.cache.mappings import slot_dict_class
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild._eapi_invalid:eapi_invalid',
)
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode

import errno
import fcntl
import io

class EbuildMetadataPhase(SubProcess):

	"""
	Asynchronous interface for the ebuild "depend" phase which is
	used to extract metadata from the ebuild.
	"""

	__slots__ = ("cpv", "eapi_supported", "ebuild_hash", "fd_pipes",
		"metadata", "portdb", "repo_path", "settings", "write_auxdb") + \
		("_eapi", "_eapi_lineno", "_raw_metadata",)

	_file_names = ("ebuild",)
	_files_dict = slot_dict_class(_file_names, prefix="")
	_metadata_fd = 9

	def _start(self):
		ebuild_path = self.ebuild_hash.location

		with io.open(_unicode_encode(ebuild_path,
			encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'],
			errors='replace') as f:
			self._eapi, self._eapi_lineno = portage._parse_eapi_ebuild_head(f)

		parsed_eapi = self._eapi
		if parsed_eapi is None:
			parsed_eapi = "0"

		if not parsed_eapi:
			# An empty EAPI setting is invalid.
			self._eapi_invalid(None)
			self._set_returncode((self.pid, 1 << 8))
			self.wait()
			return

		self.eapi_supported = portage.eapi_is_supported(parsed_eapi)
		if not self.eapi_supported:
			self.metadata = {"EAPI": parsed_eapi}
			self._set_returncode((self.pid, os.EX_OK << 8))
			self.wait()
			return

		settings = self.settings
		settings.setcpv(self.cpv)
		settings.configdict['pkg']['EAPI'] = parsed_eapi

		debug = settings.get("PORTAGE_DEBUG") == "1"
		master_fd = None
		slave_fd = None
		fd_pipes = None
		if self.fd_pipes is not None:
			fd_pipes = self.fd_pipes.copy()
		else:
			fd_pipes = {}

		null_input = open('/dev/null', 'rb')
		fd_pipes.setdefault(0, null_input.fileno())
		fd_pipes.setdefault(1, sys.__stdout__.fileno())
		fd_pipes.setdefault(2, sys.__stderr__.fileno())

		# flush any pending output
		stdout_filenos = (sys.__stdout__.fileno(), sys.__stderr__.fileno())
		for fd in fd_pipes.values():
			if fd in stdout_filenos:
				sys.__stdout__.flush()
				sys.__stderr__.flush()
				break

		self._files = self._files_dict()
		files = self._files

		master_fd, slave_fd = os.pipe()
		fcntl.fcntl(master_fd, fcntl.F_SETFL,
			fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		fd_pipes[self._metadata_fd] = slave_fd

		self._raw_metadata = []
		files.ebuild = master_fd
		self._reg_id = self.scheduler.register(files.ebuild,
			self._registered_events, self._output_handler)
		self._registered = True

		retval = portage.doebuild(ebuild_path, "depend",
			settings=settings, debug=debug,
			mydbapi=self.portdb, tree="porttree",
			fd_pipes=fd_pipes, returnpid=True)

		os.close(slave_fd)
		null_input.close()

		if isinstance(retval, int):
			# doebuild failed before spawning
			self._unregister()
			self._set_returncode((self.pid, retval << 8))
			self.wait()
			return

		self.pid = retval[0]
		portage.process.spawned_pids.remove(self.pid)

	def _output_handler(self, fd, event):

		if event & self.scheduler.IO_IN:
			while True:
				try:
					self._raw_metadata.append(
						os.read(self._files.ebuild, self._bufsize))
				except OSError as e:
					if e.errno not in (errno.EAGAIN,):
						raise
					break
				else:
					if not self._raw_metadata[-1]:
						self._unregister()
						self.wait()
						break

		self._unregister_if_appropriate(event)

		return True

	def _set_returncode(self, wait_retval):
		SubProcess._set_returncode(self, wait_retval)
		# self._raw_metadata is None when _start returns
		# early due to an unsupported EAPI
		if self.returncode == os.EX_OK and \
			self._raw_metadata is not None:
			metadata_lines = _unicode_decode(b''.join(self._raw_metadata),
				encoding=_encodings['repo.content'],
				errors='replace').splitlines()
			metadata_valid = True
			if len(portage.auxdbkeys) != len(metadata_lines):
				# Don't trust bash's returncode if the
				# number of lines is incorrect.
				metadata_valid = False
			else:
				metadata = dict(zip(portage.auxdbkeys, metadata_lines))
				parsed_eapi = self._eapi
				if parsed_eapi is None:
					parsed_eapi = "0"
				self.eapi_supported = \
					portage.eapi_is_supported(metadata["EAPI"])
				if (not metadata["EAPI"] or self.eapi_supported) and \
					metadata["EAPI"] != parsed_eapi:
					self._eapi_invalid(metadata)
					metadata_valid = False

			if metadata_valid:
				# Since we're supposed to be able to efficiently obtain the
				# EAPI from _parse_eapi_ebuild_head, we don't write cache
				# entries for unsupported EAPIs.
				if self.eapi_supported:

					if metadata.get("INHERITED", False):
						metadata["_eclasses_"] = \
							self.portdb.repositories.get_repo_for_location(
							self.repo_path).eclass_db.get_eclass_data(
							metadata["INHERITED"].split())
					else:
						metadata["_eclasses_"] = {}
					metadata.pop("INHERITED", None)

					# If called by egencache, this cache write is
					# undesirable when metadata-transfer is disabled.
					if self.write_auxdb is not False:
						self.portdb._write_cache(self.cpv,
							self.repo_path, metadata, self.ebuild_hash)
				else:
					metadata = {"EAPI": metadata["EAPI"]}
				self.metadata = metadata
			else:
				self.returncode = 1

	def _eapi_invalid(self, metadata):
		repo_name = self.portdb.getRepositoryName(self.repo_path)
		if metadata is not None:
			eapi_var = metadata["EAPI"]
		else:
			eapi_var = None
		eapi_invalid(self, self.cpv, repo_name, self.settings,
			eapi_var, self._eapi, self._eapi_lineno)
