# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.SpawnProcess import SpawnProcess
from _emerge.EbuildBuildDir import EbuildBuildDir
import sys
import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
import codecs
from portage.elog.messages import eerror
from portage.util._pty import _create_pty_or_pipe

class EbuildFetcher(SpawnProcess):

	__slots__ = ("config_pool", "fetchonly", "fetchall", "pkg", "prefetch") + \
		("_build_dir",)

	def _start(self):

		root_config = self.pkg.root_config
		portdb = root_config.trees["porttree"].dbapi
		ebuild_path = portdb.findname(self.pkg.cpv)
		if ebuild_path is None:
			raise AssertionError("ebuild not found for '%s'" % self.pkg.cpv)
		settings = self.config_pool.allocate()
		settings.setcpv(self.pkg)
		if self.prefetch and \
			self._prefetch_size_ok(portdb, settings, ebuild_path):
			self.config_pool.deallocate(settings)
			self.returncode = os.EX_OK
			self.wait()
			return

		# In prefetch mode, logging goes to emerge-fetch.log and the builddir
		# should not be touched since otherwise it could interfere with
		# another instance of the same cpv concurrently being built for a
		# different $ROOT (currently, builds only cooperate with prefetchers
		# that are spawned for the same $ROOT).
		if not self.prefetch:
			self._build_dir = EbuildBuildDir(pkg=self.pkg, settings=settings)
			self._build_dir.lock()
			self._build_dir.clean_log()
			cleanup=1
			# This initializes PORTAGE_LOG_FILE.
			portage.prepare_build_dirs(self.pkg.root, self._build_dir.settings, cleanup)
			if self.logfile is None:
				self.logfile = settings.get("PORTAGE_LOG_FILE")

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
		if nocolor is not None:
			fetch_env["NOCOLOR"] = nocolor

		fetch_env["PORTAGE_NICENESS"] = "0"
		if self.prefetch:
			fetch_env["PORTAGE_PARALLEL_FETCHONLY"] = "1"

		ebuild_binary = os.path.join(
			settings["PORTAGE_BIN_PATH"], "ebuild")

		fetch_args = [ebuild_binary, ebuild_path, phase]
		debug = settings.get("PORTAGE_DEBUG") == "1"
		if debug:
			fetch_args.append("--debug")

		if not self.background and nocolor not in ('yes', 'true'):
			# Force consistent color output, in case we are capturing fetch
			# output through a normal pipe due to unavailability of ptys.
			fetch_args.append('--color=y')

		self.args = fetch_args
		self.env = fetch_env
		if self._build_dir is None:
			# Free settings now since we only have a local reference.
			self.config_pool.deallocate(settings)
		SpawnProcess._start(self)

	def _prefetch_size_ok(self, portdb, settings, ebuild_path):
		pkgdir = os.path.dirname(ebuild_path)
		mytree = os.path.dirname(os.path.dirname(pkgdir))
		distdir = settings["DISTDIR"]
		use = None
		if not self.fetchall:
			use = self.pkg.use.enabled

		try:
			uri_map = portdb.getFetchMap(self.pkg.cpv,
				useflags=use, mytree=mytree)
		except portage.exception.InvalidDependString as e:
			return False

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

	def _set_returncode(self, wait_retval):
		SpawnProcess._set_returncode(self, wait_retval)
		# Collect elog messages that might have been
		# created by the pkg_nofetch phase.
		if self._build_dir is not None:
			# Skip elog messages for prefetch, in order to avoid duplicates.
			if not self.prefetch and self.returncode != os.EX_OK:
				elog_out = None
				if self.logfile is not None:
					if self.background:
						elog_out = codecs.open(_unicode_encode(self.logfile,
							encoding=_encodings['fs'], errors='strict'),
							mode='a', encoding=_encodings['content'], errors='replace')
				msg = "Fetch failed for '%s'" % (self.pkg.cpv,)
				if self.logfile is not None:
					msg += ", Log file:"
				eerror(msg, phase="unpack", key=self.pkg.cpv, out=elog_out)
				if self.logfile is not None:
					eerror(" '%s'" % (self.logfile,),
						phase="unpack", key=self.pkg.cpv, out=elog_out)
				if elog_out is not None:
					elog_out.close()
			if not self.prefetch:
				portage.elog.elog_process(self.pkg.cpv, self._build_dir.settings)
			features = self._build_dir.settings.features
			if self.returncode == os.EX_OK:
				self._build_dir.clean_log()
			self._build_dir.unlock()
			self.config_pool.deallocate(self._build_dir.settings)
			self._build_dir = None

