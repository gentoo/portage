# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import traceback

from _emerge.SpawnProcess import SpawnProcess
import copy
import signal
import sys
import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage import _unicode_decode
import codecs
from portage.elog.messages import eerror
from portage.package.ebuild.fetch import fetch
from portage.util._pty import _create_pty_or_pipe

class EbuildFetcher(SpawnProcess):

	__slots__ = ("config_pool", "fetchonly", "fetchall", "pkg", "prefetch") + \
		("_digests", "_settings", "_uri_map")

	def _start(self):

		root_config = self.pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		ebuild_path = portdb.findname(self.pkg.cpv)
		if ebuild_path is None:
			raise AssertionError("ebuild not found for '%s'" % self.pkg.cpv)

		try:
			uri_map = self._get_uri_map(portdb, ebuild_path)
		except portage.exception.InvalidDependString as e:
			msg_lines = []
			msg = "Fetch failed for '%s' due to invalid SRC_URI: %s" % \
				(self.pkg.cpv, e)
			msg_lines.append(msg)
			self._eerror(msg_lines)
			self._set_returncode((self.pid, 1))
			self.wait()
			return

		if not uri_map:
			# Nothing to fetch.
			self._set_returncode((self.pid, os.EX_OK))
			self.wait()
			return

		self._digests = portage.Manifest(
			os.path.dirname(ebuild_path), None).getTypeDigests("DIST")

		settings = self.config_pool.allocate()
		settings.setcpv(self.pkg)
		portage.doebuild_environment(ebuild_path, 'fetch',
			settings=settings, db=portdb)

		if self.prefetch and \
			self._prefetch_size_ok(uri_map, settings, ebuild_path):
			self.config_pool.deallocate(settings)
			self._set_returncode((self.pid, os.EX_OK))
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
		self._uri_map = uri_map
		SpawnProcess._start(self)

		# Free settings now since it's no longer needed in
		# this process (the subprocess has a private copy).
		self.config_pool.deallocate(settings)
		settings = None
		self._settings = None

	def _spawn(self, args, fd_pipes=None, **kwargs):
		"""
		Fork a subprocess, apply local settings, and call fetch().
		"""

		pid = os.fork()
		if pid != 0:
			portage.process.spawned_pids.append(pid)
			return [pid]

		portage.process._setup_pipes(fd_pipes)

		# Use default signal handlers in order to avoid problems
		# killing subprocesses as reported in bug #353239.
		signal.signal(signal.SIGINT, signal.SIG_DFL)
		signal.signal(signal.SIGTERM, signal.SIG_DFL)

		# Force consistent color output, in case we are capturing fetch
		# output through a normal pipe due to unavailability of ptys.
		portage.output.havecolor = self._settings.get('NOCOLOR') \
			not in ('yes', 'true')

		rval = 1
		try:
			if fetch(self._uri_map, self._settings, fetchonly=self.fetchonly,
				digests=copy.deepcopy(self._digests),
				allow_missing_digests=False):
				rval = os.EX_OK
		except SystemExit:
			raise
		except:
			traceback.print_exc()
		finally:
			# Call os._exit() from finally block, in order to suppress any
			# finally blocks from earlier in the call stack. See bug #345289.
			os._exit(rval)

	def _get_uri_map(self, portdb, ebuild_path):
		"""
		This can raise InvalidDependString from portdbapi.getFetchMap().
		"""
		pkgdir = os.path.dirname(ebuild_path)
		mytree = os.path.dirname(os.path.dirname(pkgdir))
		use = None
		if not self.fetchall:
			use = self.pkg.use.enabled
		return portdb.getFetchMap(self.pkg.cpv, useflags=use, mytree=mytree)

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

		digests = self._digests
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
			f = codecs.open(_unicode_encode(self.logfile,
				encoding=_encodings['fs'], errors='strict'),
				mode='a', encoding=_encodings['content'], errors='replace')
			for filename in uri_map:
				f.write((' * %s size ;-) ...' % \
					filename).ljust(73) + '[ ok ]\n')
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
		out = portage.StringIO()
		for line in lines:
			eerror(line, phase="unpack", key=self.pkg.cpv, out=out)
		msg = _unicode_decode(out.getvalue(),
			encoding=_encodings['content'], errors='replace')
		if msg:
			self.scheduler.output(msg, log_path=self.logfile)

	def _set_returncode(self, wait_retval):
		SpawnProcess._set_returncode(self, wait_retval)
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
