# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import copy
import io
import sys

import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage import _unicode_decode
from portage.checksum import _hash_filter
from portage.elog.messages import eerror
from portage.package.ebuild.fetch import (
	_check_distfile,
	_drop_privs_userfetch,
	_want_userfetch,
	fetch,
)
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture
from portage.util._async.ForkProcess import ForkProcess
from portage.util._pty import _create_pty_or_pipe
from _emerge.CompositeTask import CompositeTask


class EbuildFetcher(CompositeTask):

	__slots__ = ("config_pool", "ebuild_path", "fetchonly", "fetchall",
		"logfile", "pkg", "prefetch", "_fetcher_proc")

	def __init__(self, **kwargs):
		CompositeTask.__init__(self, **kwargs)
		self._fetcher_proc = _EbuildFetcherProcess(**kwargs)

	def async_already_fetched(self, settings):
		"""
		Returns True if all files already exist locally and have correct
		digests, otherwise return False. When returning True, appropriate
		digest checking messages are produced for display and/or logging.
		When returning False, no messages are produced, since we assume
		that a fetcher process will later be executed in order to produce
		such messages. This will raise InvalidDependString if SRC_URI is
		invalid.
		"""
		return self._fetcher_proc.async_already_fetched(settings)

	def _start(self):
		self._start_task(
			AsyncTaskFuture(future=self._fetcher_proc._async_uri_map()),
			self._start_fetch)

	def _start_fetch(self, uri_map_task):
		self._assert_current(uri_map_task)
		if uri_map_task.cancelled:
			self._default_final_exit(uri_map_task)
			return

		try:
			uri_map = uri_map_task.future.result()
		except portage.exception.InvalidDependString as e:
			msg_lines = []
			msg = "Fetch failed for '%s' due to invalid SRC_URI: %s" % \
				(self.pkg.cpv, e)
			msg_lines.append(msg)
			self._fetcher_proc._eerror(msg_lines)
			self._current_task = None
			self.returncode = 1
			self._async_wait()
			return

		# First get the SRC_URI metadata (it's not cached in self.pkg.metadata
		# because some packages have an extremely large SRC_URI value).
		self._start_task(
			AsyncTaskFuture(
				future=self.pkg.root_config.trees["porttree"].dbapi.\
				async_aux_get(self.pkg.cpv, ["SRC_URI"], myrepo=self.pkg.repo,
				loop=self.scheduler)),
			self._start_with_metadata)

	def _start_with_metadata(self, aux_get_task):
		self._assert_current(aux_get_task)
		if aux_get_task.cancelled:
			self._default_final_exit(aux_get_task)
			return

		self._fetcher_proc.src_uri, = aux_get_task.future.result()
		self._start_task(self._fetcher_proc, self._default_final_exit)


class _EbuildFetcherProcess(ForkProcess):

	__slots__ = ("config_pool", "ebuild_path", "fetchonly", "fetchall",
		"pkg", "prefetch", "src_uri", "_digests", "_manifest",
		"_settings", "_uri_map")

	def async_already_fetched(self, settings):
		result = self.scheduler.create_future()

		def uri_map_done(uri_map_future):
			if uri_map_future.cancelled():
				result.cancel()
				return

			if uri_map_future.exception() is not None or result.cancelled():
				if not result.cancelled():
					result.set_exception(uri_map_future.exception())
				return

			uri_map = uri_map_future.result()
			if uri_map:
				result.set_result(
					self._check_already_fetched(settings, uri_map))
			else:
				result.set_result(True)

		uri_map_future = self._async_uri_map()
		result.add_done_callback(lambda result:
			uri_map_future.cancel() if result.cancelled() else None)
		uri_map_future.add_done_callback(uri_map_done)
		return result

	def _check_already_fetched(self, settings, uri_map):
		digests = self._get_digests()
		distdir = settings["DISTDIR"]
		allow_missing = self._get_manifest().allow_missing

		for filename in uri_map:
			# Use stat rather than lstat since fetch() creates
			# symlinks when PORTAGE_RO_DISTDIRS is used.
			try:
				st = os.stat(os.path.join(distdir, filename))
			except OSError:
				return False
			if st.st_size == 0:
				return False
			expected_size = digests.get(filename, {}).get('size')
			if expected_size is None:
				continue
			if st.st_size != expected_size:
				return False

		hash_filter = _hash_filter(settings.get("PORTAGE_CHECKSUM_FILTER", ""))
		if hash_filter.transparent:
			hash_filter = None
		stdout_orig = sys.stdout
		stderr_orig = sys.stderr
		global_havecolor = portage.output.havecolor
		out = io.StringIO()
		eout = portage.output.EOutput()
		eout.quiet = settings.get("PORTAGE_QUIET") == "1"
		success = True
		try:
			sys.stdout = out
			sys.stderr = out
			if portage.output.havecolor:
				portage.output.havecolor = not self.background

			for filename in uri_map:
				mydigests = digests.get(filename)
				if mydigests is None:
					if not allow_missing:
						success = False
						break
					continue
				ok, st = _check_distfile(os.path.join(distdir, filename),
					mydigests, eout, show_errors=False, hash_filter=hash_filter)
				if not ok:
					success = False
					break
		except portage.exception.FileNotFound:
			# A file disappeared unexpectedly.
			return False
		finally:
			sys.stdout = stdout_orig
			sys.stderr = stderr_orig
			portage.output.havecolor = global_havecolor

		if success:
			# When returning unsuccessfully, no messages are produced, since
			# we assume that a fetcher process will later be executed in order
			# to produce such messages.
			msg = out.getvalue()
			if msg:
				self.scheduler.output(msg, log_path=self.logfile)

		return success

	def _start(self):

		root_config = self.pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		ebuild_path = self._get_ebuild_path()
		# This is initialized by an earlier _async_uri_map call.
		uri_map = self._uri_map

		if not uri_map:
			# Nothing to fetch.
			self.returncode = os.EX_OK
			self._async_wait()
			return

		settings = self.config_pool.allocate()
		settings.setcpv(self.pkg)
		settings.configdict["pkg"]["SRC_URI"] = self.src_uri
		portage.doebuild_environment(ebuild_path, 'fetch',
			settings=settings, db=portdb)

		if self.prefetch and \
			self._prefetch_size_ok(uri_map, settings, ebuild_path):
			self.config_pool.deallocate(settings)
			self.returncode = os.EX_OK
			self._async_wait()
			return

		nocolor = settings.get("NOCOLOR")

		if self.prefetch:
			settings["PORTAGE_PARALLEL_FETCHONLY"] = "1"

		if self.background:
			nocolor = "true"

		if nocolor is not None:
			settings["NOCOLOR"] = nocolor

		self._settings = settings
		self.log_filter_file = settings.get('PORTAGE_LOG_FILTER_FILE_CMD')
		ForkProcess._start(self)

		# Free settings now since it's no longer needed in
		# this process (the subprocess has a private copy).
		self.config_pool.deallocate(settings)
		settings = None
		self._settings = None

	def _run(self):
		# Force consistent color output, in case we are capturing fetch
		# output through a normal pipe due to unavailability of ptys.
		portage.output.havecolor = self._settings.get('NOCOLOR') \
			not in ('yes', 'true')

		# For userfetch, drop privileges for the entire fetch call, in
		# order to handle DISTDIR on NFS with root_squash for bug 601252.
		if _want_userfetch(self._settings):
			_drop_privs_userfetch(self._settings)

		rval = 1
		allow_missing = self._get_manifest().allow_missing or \
			'digest' in self._settings.features
		if fetch(self._uri_map, self._settings, fetchonly=self.fetchonly,
			digests=copy.deepcopy(self._get_digests()),
			allow_missing_digests=allow_missing):
			rval = os.EX_OK
		return rval

	def _get_ebuild_path(self):
		if self.ebuild_path is not None:
			return self.ebuild_path
		portdb = self.pkg.root_config.trees["porttree"].dbapi
		self.ebuild_path = portdb.findname(self.pkg.cpv, myrepo=self.pkg.repo)
		if self.ebuild_path is None:
			raise AssertionError("ebuild not found for '%s'" % self.pkg.cpv)
		return self.ebuild_path

	def _get_manifest(self):
		if self._manifest is None:
			pkgdir = os.path.dirname(self._get_ebuild_path())
			self._manifest = self.pkg.root_config.settings.repositories.get_repo_for_location(
				os.path.dirname(os.path.dirname(pkgdir))).load_manifest(pkgdir, None)
		return self._manifest

	def _get_digests(self):
		if self._digests is None:
			self._digests = self._get_manifest().getTypeDigests("DIST")
		return self._digests

	def _async_uri_map(self):
		"""
		This calls the portdbapi.async_fetch_map method and returns the
		resulting Future (may contain InvalidDependString exception).
		"""
		if self._uri_map is not None:
			result = self.scheduler.create_future()
			result.set_result(self._uri_map)
			return result

		pkgdir = os.path.dirname(self._get_ebuild_path())
		mytree = os.path.dirname(os.path.dirname(pkgdir))
		use = None
		if not self.fetchall:
			use = self.pkg.use.enabled
		portdb = self.pkg.root_config.trees["porttree"].dbapi

		def cache_result(result):
			try:
				self._uri_map = result.result()
			except Exception:
				# The caller handles this when it retrieves the result.
				pass

		result = portdb.async_fetch_map(self.pkg.cpv,
			useflags=use, mytree=mytree, loop=self.scheduler)
		result.add_done_callback(cache_result)
		return result

	def _prefetch_size_ok(self, uri_map, settings, ebuild_path):
		distdir = settings["DISTDIR"]

		sizes = {}
		for filename in uri_map:
			# Use stat rather than lstat since portage.fetch() creates
			# symlinks when PORTAGE_RO_DISTDIRS is used.
			try:
				st = os.stat(os.path.join(distdir, filename))
			except OSError:
				return False
			if st.st_size == 0:
				return False
			sizes[filename] = st.st_size

		digests = self._get_digests()
		for filename, actual_size in sizes.items():
			size = digests.get(filename, {}).get('size')
			if size is None:
				continue
			if size != actual_size:
				return False

		# All files are present and sizes are ok. In this case the normal
		# fetch code will be skipped, so we need to generate equivalent
		# output here.
		if self.logfile is not None:
			f = io.open(_unicode_encode(self.logfile,
				encoding=_encodings['fs'], errors='strict'),
				mode='a', encoding=_encodings['content'],
				errors='backslashreplace')
			for filename in uri_map:
				f.write(_unicode_decode((' * %s size ;-) ...' % \
					filename).ljust(73) + '[ ok ]\n'))
			f.close()

		return True

	def _pipe(self, fd_pipes):
		"""When appropriate, use a pty so that fetcher progress bars,
		like wget has, will work properly."""
		if self.background or not sys.stdout.isatty():
			# When the output only goes to a log file,
			# there's no point in creating a pty.
			return os.pipe()
		stdout_pipe = None
		if not self.background:
			stdout_pipe = fd_pipes.get(1)
		got_pty, master_fd, slave_fd = \
			_create_pty_or_pipe(copy_term_size=stdout_pipe)
		return (master_fd, slave_fd)

	def _eerror(self, lines):
		out = io.StringIO()
		for line in lines:
			eerror(line, phase="unpack", key=self.pkg.cpv, out=out)
		msg = out.getvalue()
		if msg:
			self.scheduler.output(msg, log_path=self.logfile)

	def _proc_join_done(self, proc, future):
		"""
		Extend _proc_join_done to emit an eerror message for fetch failure.
		"""
		if not self.prefetch and not future.cancelled() and proc.exitcode != os.EX_OK:
			msg_lines = []
			msg = "Fetch failed for '%s'" % (self.pkg.cpv,)
			if self.logfile is not None:
				msg += ", Log file:"
			msg_lines.append(msg)
			if self.logfile is not None:
				msg_lines.append(" '%s'" % (self.logfile,))
			self._eerror(msg_lines)
		super(_EbuildFetcherProcess, self)._proc_join_done(proc, future)
