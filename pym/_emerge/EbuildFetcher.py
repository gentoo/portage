# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from _emerge.SpawnProcess import SpawnProcess
from _emerge.EbuildBuildDir import EbuildBuildDir
import sys
import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
import codecs
from portage.elog.messages import eerror

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

		# In prefetch mode, logging goes to emerge-fetch.log and the builddir
		# should not be touched since otherwise it could interfere with
		# another instance of the same cpv concurrently being built for a
		# different $ROOT (currently, builds only cooperate with prefetchers
		# that are spawned for the same $ROOT).
		if not self.prefetch:
			self._build_dir = EbuildBuildDir(pkg=self.pkg, settings=settings)
			self._build_dir.lock()
			self._build_dir.clean_log()
			portage.prepare_build_dirs(self.pkg.root, self._build_dir.settings, 0)
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

		self.args = fetch_args
		self.env = fetch_env
		SpawnProcess._start(self)

	def _pipe(self, fd_pipes):
		"""When appropriate, use a pty so that fetcher progress bars,
		like wget has, will work properly."""
		if self.background or not sys.stdout.isatty():
			# When the output only goes to a log file,
			# there's no point in creating a pty.
			return os.pipe()
		stdout_pipe = fd_pipes.get(1)
		got_pty, master_fd, slave_fd = \
			portage._create_pty_or_pipe(copy_term_size=stdout_pipe)
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

