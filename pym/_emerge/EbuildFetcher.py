# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SpawnProcess import SpawnProcess
import sys
import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage import _unicode_decode
import codecs
from portage.elog.messages import eerror
from portage.util._pty import _create_pty_or_pipe

class EbuildFetcher(SpawnProcess):

	__slots__ = ("config_pool", "fetchonly", "fetchall", "pkg", "prefetch")

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

		settings = self.config_pool.allocate()
		settings.setcpv(self.pkg)

		if self.prefetch and \
			self._prefetch_size_ok(uri_map, settings, ebuild_path):
			self.config_pool.deallocate(settings)
			self._set_returncode((self.pid, os.EX_OK))
			self.wait()
			return

		phase = "fetch"
		if self.fetchall:
			phase = "fetchall"

		# If any incremental variables have been overridden
		# via the environment, those values need to be passed
		# along here so that they are correctly considered by
		# the config instance in the subproccess.
		fetch_env = os.environ.copy()
		fetch_env['PORTAGE_CONFIGROOT'] = settings['PORTAGE_CONFIGROOT']

		nocolor = settings.get("NOCOLOR")

		if self.prefetch:
			fetch_env["PORTAGE_PARALLEL_FETCHONLY"] = "1"
			# prefetch always outputs to a log, so
			# always disable color
			nocolor = "true"

		if nocolor is not None:
			fetch_env["NOCOLOR"] = nocolor

		fetch_env["PORTAGE_NICENESS"] = "0"

		ebuild_binary = os.path.join(
			settings["PORTAGE_BIN_PATH"], "ebuild")

		fetch_args = [ebuild_binary, ebuild_path, phase]
		debug = settings.get("PORTAGE_DEBUG") == "1"
		if debug:
			fetch_args.append("--debug")

		# Free settings now since we only have a local reference.
		self.config_pool.deallocate(settings)
		settings = None

		if not self.background and nocolor not in ('yes', 'true'):
			# Force consistent color output, in case we are capturing fetch
			# output through a normal pipe due to unavailability of ptys.
			fetch_args.append('--color=y')

		self.args = fetch_args
		self.env = fetch_env
		SpawnProcess._start(self)

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
		pkgdir = os.path.dirname(ebuild_path)
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

		digests = portage.Manifest(pkgdir, distdir).getTypeDigests("DIST")
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
