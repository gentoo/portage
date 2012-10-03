# Copyright 1999-2012 Gentoo Foundation
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
from portage.package.ebuild.fetch import _check_distfile, fetch
from portage.util._async.ForkProcess import ForkProcess
from portage.util._pty import _create_pty_or_pipe

class EbuildFetcher(ForkProcess):

	__slots__ = ("config_pool", "ebuild_path", "fetchonly", "fetchall",
		"pkg", "prefetch") + \
		("_digests", "_manifest", "_settings", "_uri_map")

	def already_fetched(self, settings):
		"""
		Returns True if all files already exist locally and have correct
		digests, otherwise return False. When returning True, appropriate
		digest checking messages are produced for display and/or logging.
		When returning False, no messages are produced, since we assume
		that a fetcher process will later be executed in order to produce
		such messages. This will raise InvalidDependString if SRC_URI is
		invalid.
		"""

		uri_map = self._get_uri_map()
		if not uri_map:
			return True

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

		try:
			uri_map = self._get_uri_map()
		except portage.exception.InvalidDependString as e:
			msg_lines = []
			msg = "Fetch failed for '%s' due to invalid SRC_URI: %s" % \
				(self.pkg.cpv, e)
			msg_lines.append(msg)
			self._eerror(msg_lines)
			self._set_returncode((self.pid, 1 << 8))
			self.wait()
			return

		if not uri_map:
			# Nothing to fetch.
			self._set_returncode((self.pid, os.EX_OK << 8))
			self.wait()
			return

		settings = self.config_pool.allocate()
		settings.setcpv(self.pkg)
		portage.doebuild_environment(ebuild_path, 'fetch',
			settings=settings, db=portdb)

		if self.prefetch and \
			self._prefetch_size_ok(uri_map, settings, ebuild_path):
			self.config_pool.deallocate(settings)
			self._set_returncode((self.pid, os.EX_OK << 8))
			self.wait()
			return

		nocolor = settings.get("NOCOLOR")

		if self.prefetch:
			settings["PORTAGE_PARALLEL_FETCHONLY"] = "1"

		if self.background:
			nocolor = "true"

		if nocolor is not None:
			settings["NOCOLOR"] = nocolor

		self._settings = settings
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

		rval = 1
		allow_missing = self._get_manifest().allow_missing
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

	def _get_uri_map(self):
		"""
		This can raise InvalidDependString from portdbapi.getFetchMap().
		"""
		if self._uri_map is not None:
			return self._uri_map
		pkgdir = os.path.dirname(self._get_ebuild_path())
		mytree = os.path.dirname(os.path.dirname(pkgdir))
		use = None
		if not self.fetchall:
			use = self.pkg.use.enabled
		portdb = self.pkg.root_config.trees["porttree"].dbapi
		self._uri_map = portdb.getFetchMap(self.pkg.cpv,
			useflags=use, mytree=mytree)
		return self._uri_map

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

	def _set_returncode(self, wait_retval):
		ForkProcess._set_returncode(self, wait_retval)
		# Collect elog messages that might have been
		# created by the pkg_nofetch phase.
		# Skip elog messages for prefetch, in order to avoid duplicates.
		if not self.prefetch and self.returncode != os.EX_OK:
			msg_lines = []
			msg = "Fetch failed for '%s'" % (self.pkg.cpv,)
			if self.logfile is not None:
				msg += ", Log file:"
			msg_lines.append(msg)
			if self.logfile is not None:
				msg_lines.append(" '%s'" % (self.logfile,))
			self._eerror(msg_lines)
