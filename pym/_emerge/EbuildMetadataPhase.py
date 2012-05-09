# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SubProcess import SubProcess
import sys
from portage.cache.mappings import slot_dict_class
import portage
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.dep import _repo_separator
from portage.elog import elog_process
from portage.elog.messages import eerror
import errno
import fcntl
import io
import textwrap

class EbuildMetadataPhase(SubProcess):

	"""
	Asynchronous interface for the ebuild "depend" phase which is
	used to extract metadata from the ebuild.
	"""

	__slots__ = ("cpv", "ebuild_hash", "fd_pipes",
		"metadata_callback", "metadata", "portdb", "repo_path", "settings") + \
		("_eapi", "_eapi_lineno", "_raw_metadata",)

	_file_names = ("ebuild",)
	_files_dict = slot_dict_class(_file_names, prefix="")
	_metadata_fd = 9

	def _start(self):
		settings = self.settings
		settings.setcpv(self.cpv)
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

		if not portage.eapi_is_supported(parsed_eapi):
			self.metadata = self.metadata_callback(self.cpv,
				self.repo_path, {'EAPI' : parsed_eapi}, self.ebuild_hash)
			self._set_returncode((self.pid, os.EX_OK << 8))
			self.wait()
			return

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
		fd_pipes.setdefault(1, sys.stdout.fileno())
		fd_pipes.setdefault(2, sys.stderr.fileno())

		# flush any pending output
		for fd in fd_pipes.values():
			if fd == sys.stdout.fileno():
				sys.stdout.flush()
			if fd == sys.stderr.fileno():
				sys.stderr.flush()

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
		# early due to an unsupported EAPI detected with
		# FEATURES=parse-eapi-ebuild-head
		if self.returncode == os.EX_OK and \
			self._raw_metadata is not None:
			metadata_lines = _unicode_decode(b''.join(self._raw_metadata),
				encoding=_encodings['repo.content'],
				errors='replace').splitlines()
			if len(portage.auxdbkeys) != len(metadata_lines):
				# Don't trust bash's returncode if the
				# number of lines is incorrect.
				self.returncode = 1
			else:
				metadata_valid = True
				metadata = dict(zip(portage.auxdbkeys, metadata_lines))
				parsed_eapi = self._eapi
				if parsed_eapi is None:
					parsed_eapi = "0"
				if portage.eapi_is_supported(metadata["EAPI"]) and \
					metadata["EAPI"] != parsed_eapi:
					self._eapi_invalid(metadata)
					if 'parse-eapi-ebuild-head' in self.settings.features:
						metadata_valid = False

				if metadata_valid:
					self.metadata = self.metadata_callback(self.cpv,
						self.repo_path, metadata, self.ebuild_hash)
				else:
					self.returncode = 1

	def _eapi_invalid(self, metadata):

		repo_name = self.portdb.getRepositoryName(self.repo_path)

		msg = []
		msg.extend(textwrap.wrap(("EAPI assignment in ebuild '%s%s%s' does not"
			" conform with PMS section 7.3.1:") %
			(self.cpv, _repo_separator, repo_name), 70))

		if not self._eapi:
			# None means the assignment was not found, while an
			# empty string indicates an (invalid) empty assingment.
			msg.append(
				"\tvalid EAPI assignment must"
				" occur on or before line: %s" %
				self._eapi_lineno)
		else:
			msg.append(("\tbash returned EAPI '%s' which does not match "
				"assignment on line: %s") %
				(metadata["EAPI"], self._eapi_lineno))

		if 'parse-eapi-ebuild-head' in self.settings.features:
			msg.extend(textwrap.wrap(("NOTE: This error will soon"
				" become unconditionally fatal in a future version of Portage,"
				" but at this time, it can by made non-fatal by setting"
				" FEATURES=-parse-eapi-ebuild-head in"
				" make.conf."), 70))
		else:
			msg.extend(textwrap.wrap(("NOTE: This error will soon"
				" become unconditionally fatal in a future version of Portage."
				" At the earliest opportunity, please enable"
				" FEATURES=parse-eapi-ebuild-head in make.conf in order to"
				" make this error fatal."), 70))

		for line in msg:
			eerror(line, phase="other", key=self.cpv)
		elog_process(self.cpv, self.settings,
			phasefilter=("other",))
