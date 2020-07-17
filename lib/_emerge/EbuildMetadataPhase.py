# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.SubProcess import SubProcess
import sys
from portage.cache.mappings import slot_dict_class
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild._metadata_invalid:eapi_invalid',
)
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.dep import extract_unpack_dependencies
from portage.eapi import eapi_has_automatic_unpack_dependencies

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
			self.returncode = 1
			self._async_wait()
			return

		self.eapi_supported = portage.eapi_is_supported(parsed_eapi)
		if not self.eapi_supported:
			self.metadata = {"EAPI": parsed_eapi}
			self.returncode = os.EX_OK
			self._async_wait()
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

		fd_pipes[slave_fd] = slave_fd
		settings["PORTAGE_PIPE_FD"] = str(slave_fd)

		self._raw_metadata = []
		files.ebuild = master_fd
		self.scheduler.add_reader(files.ebuild, self._output_handler)
		self._registered = True

		retval = portage.doebuild(ebuild_path, "depend",
			settings=settings, debug=debug,
			mydbapi=self.portdb, tree="porttree",
			fd_pipes=fd_pipes, returnpid=True)
		settings.pop("PORTAGE_PIPE_FD", None)

		os.close(slave_fd)
		null_input.close()

		if isinstance(retval, int):
			# doebuild failed before spawning
			self.returncode = retval
			self._async_wait()
			return

		self.pid = retval[0]

	def _output_handler(self):
		while True:
			buf = self._read_buf(self._files.ebuild)
			if buf is None:
				break # EAGAIN
			elif buf:
				self._raw_metadata.append(buf)
			else: # EIO/POLLHUP
						if self.pid is None:
							self._unregister()
							self._async_wait()
						else:
							self._async_waitpid()
						break

	def _unregister(self):
		if self._files is not None:
			self.scheduler.remove_reader(self._files.ebuild)
		SubProcess._unregister(self)

	def _async_waitpid_cb(self, *args, **kwargs):
		"""
		Override _async_waitpid_cb to perform cleanup that is
		not necessarily idempotent.
		"""
		SubProcess._async_waitpid_cb(self, *args, **kwargs)
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

					if eapi_has_automatic_unpack_dependencies(metadata["EAPI"]):
						repo = self.portdb.repositories.get_name_for_location(self.repo_path)
						unpackers = self.settings.unpack_dependencies.get(repo, {}).get(metadata["EAPI"], {})
						unpack_dependencies = extract_unpack_dependencies(metadata["SRC_URI"], unpackers)
						if unpack_dependencies:
							metadata["DEPEND"] += (" " if metadata["DEPEND"] else "") + unpack_dependencies

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
