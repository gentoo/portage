# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
import platform

import fcntl
import portage
from portage import os, _unicode_decode
from portage.util._ctypes import find_library
import portage.elog.messages
from portage.util._async.ForkProcess import ForkProcess

class MergeProcess(ForkProcess):
	"""
	Merge packages in a subprocess, so the Scheduler can run in the main
	thread while files are moved or copied asynchronously.
	"""

	__slots__ = ('mycat', 'mypkg', 'settings', 'treetype',
		'vartree', 'blockers', 'pkgloc', 'infloc', 'myebuild',
		'mydbapi', 'postinst_failure', 'prev_mtimes', 'unmerge',
		'_elog_reader_fd',
		'_buf', '_counter', '_dblink', '_elog_keys', '_locked_vdb')

	def _start(self):
		# Portage should always call setcpv prior to this
		# point, but here we have a fallback as a convenience
		# for external API consumers. It's important that
		# this metadata access happens in the parent process,
		# since closing of file descriptors in the subprocess
		# can prevent access to open database connections such
		# as that used by the sqlite metadata cache module.
		cpv = "%s/%s" % (self.mycat, self.mypkg)
		settings = self.settings
		if cpv != settings.mycpv or \
			"EAPI" not in settings.configdict["pkg"]:
			settings.reload()
			settings.reset()
			settings.setcpv(cpv, mydb=self.mydbapi)

		# This caches the libc library lookup in the current
		# process, so that it's only done once rather than
		# for each child process.
		if platform.system() == "Linux" and \
			"merge-sync" in settings.features:
			find_library("c")

		# Inherit stdin by default, so that the pdb SIGUSR1
		# handler is usable for the subprocess.
		if self.fd_pipes is None:
			self.fd_pipes = {}
		else:
			self.fd_pipes = self.fd_pipes.copy()
		self.fd_pipes.setdefault(0, portage._get_stdin().fileno())

		self.log_filter_file = self.settings.get('PORTAGE_LOG_FILTER_FILE_CMD')
		super(MergeProcess, self)._start()

	def _lock_vdb(self):
		"""
		Lock the vdb if FEATURES=parallel-install is NOT enabled,
		otherwise do nothing. This is implemented with
		vardbapi.lock(), which supports reentrance by the
		subprocess that we spawn.
		"""
		if "parallel-install" not in self.settings.features:
			self.vartree.dbapi.lock()
			self._locked_vdb = True

	def _unlock_vdb(self):
		"""
		Unlock the vdb if we hold a lock, otherwise do nothing.
		"""
		if self._locked_vdb:
			self.vartree.dbapi.unlock()
			self._locked_vdb = False

	def _elog_output_handler(self):
		output = self._read_buf(self._elog_reader_fd)
		if output:
			lines = _unicode_decode(output).split('\n')
			if len(lines) == 1:
				self._buf += lines[0]
			else:
				lines[0] = self._buf + lines[0]
				self._buf = lines.pop()
				out = io.StringIO()
				for line in lines:
					funcname, phase, key, msg = line.split(' ', 3)
					self._elog_keys.add(key)
					reporter = getattr(portage.elog.messages, funcname)
					reporter(msg, phase=phase, key=key, out=out)

		elif output is not None: # EIO/POLLHUP
			self.scheduler.remove_reader(self._elog_reader_fd)
			os.close(self._elog_reader_fd)
			self._elog_reader_fd = None
			return False

	def _spawn(self, args, fd_pipes, **kwargs):
		"""
		Extend the superclass _spawn method to perform some pre-fork and
		post-fork actions.
		"""

		elog_reader_fd, elog_writer_fd = os.pipe()

		fcntl.fcntl(elog_reader_fd, fcntl.F_SETFL,
			fcntl.fcntl(elog_reader_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

		blockers = None
		if self.blockers is not None:
			# Query blockers in the main process, since closing
			# of file descriptors in the subprocess can prevent
			# access to open database connections such as that
			# used by the sqlite metadata cache module.
			blockers = self.blockers()
		mylink = portage.dblink(self.mycat, self.mypkg, settings=self.settings,
			treetype=self.treetype, vartree=self.vartree,
			blockers=blockers, pipe=elog_writer_fd)
		fd_pipes[elog_writer_fd] = elog_writer_fd
		self.scheduler.add_reader(elog_reader_fd, self._elog_output_handler)

		# If a concurrent emerge process tries to install a package
		# in the same SLOT as this one at the same time, there is an
		# extremely unlikely chance that the COUNTER values will not be
		# ordered correctly unless we lock the vdb here.
		# FEATURES=parallel-install skips this lock in order to
		# improve performance, and the risk is practically negligible.
		self._lock_vdb()
		if not self.unmerge:
			self._counter = self.vartree.dbapi.counter_tick()

		self._dblink = mylink
		self._elog_reader_fd = elog_reader_fd
		pids = super(MergeProcess, self)._spawn(args, fd_pipes, **kwargs)
		os.close(elog_writer_fd)
		self._buf = ""
		self._elog_keys = set()
		# Discard messages which will be collected by the subprocess,
		# in order to avoid duplicates (bug #446136).
		portage.elog.messages.collect_messages(key=mylink.mycpv)

		# invalidate relevant vardbapi caches
		if self.vartree.dbapi._categories is not None:
			self.vartree.dbapi._categories = None
		self.vartree.dbapi._pkgs_changed = True
		self.vartree.dbapi._clear_pkg_cache(mylink)

		return pids

	def _run(self):
			os.close(self._elog_reader_fd)
			counter = self._counter
			mylink = self._dblink

			portage.output.havecolor = self.settings.get('NOCOLOR') \
				not in ('yes', 'true')

			# Avoid wastful updates of the vdb cache.
			self.vartree.dbapi._flush_cache_enabled = False

			# In this subprocess we don't want PORTAGE_BACKGROUND to
			# suppress stdout/stderr output since they are pipes. We
			# also don't want to open PORTAGE_LOG_FILE, since it will
			# already be opened by the parent process, so we set the
			# "subprocess" value for use in conditional logging code
			# involving PORTAGE_LOG_FILE.
			if not self.unmerge:
				# unmerge phases have separate logs
				if self.settings.get("PORTAGE_BACKGROUND") == "1":
					self.settings["PORTAGE_BACKGROUND_UNMERGE"] = "1"
				else:
					self.settings["PORTAGE_BACKGROUND_UNMERGE"] = "0"
				self.settings.backup_changes("PORTAGE_BACKGROUND_UNMERGE")
			self.settings["PORTAGE_BACKGROUND"] = "subprocess"
			self.settings.backup_changes("PORTAGE_BACKGROUND")

			rval = 1
			if self.unmerge:
					if not mylink.exists():
						rval = os.EX_OK
					elif mylink.unmerge(
						ldpath_mtimes=self.prev_mtimes) == os.EX_OK:
						mylink.lockdb()
						try:
							mylink.delete()
						finally:
							mylink.unlockdb()
						rval = os.EX_OK
			else:
					rval = mylink.merge(self.pkgloc, self.infloc,
						myebuild=self.myebuild, mydbapi=self.mydbapi,
						prev_mtimes=self.prev_mtimes, counter=counter)
			return rval

	def _proc_join_done(self, proc, future):
		"""
		Extend _proc_join_done to react to RETURNCODE_POSTINST_FAILURE.
		"""
		if not future.cancelled() and proc.exitcode == portage.const.RETURNCODE_POSTINST_FAILURE:
			self.postinst_failure = True
			self.returncode = os.EX_OK
		super(MergeProcess, self)._proc_join_done(proc, future)

	def _unregister(self):
		"""
		Unregister from the scheduler and close open files.
		"""

		if not self.unmerge:
			# Populate the vardbapi cache for the new package
			# while its inodes are still hot.
			try:
				self.vartree.dbapi.aux_get(self.settings.mycpv, ["EAPI"])
			except KeyError:
				pass

		self._unlock_vdb()
		if self._elog_reader_fd is not None:
			self.scheduler.remove_reader(self._elog_reader_fd)
			os.close(self._elog_reader_fd)
			self._elog_reader_fd = None
		if self._elog_keys is not None:
			for key in self._elog_keys:
				portage.elog.elog_process(key, self.settings,
					phasefilter=("prerm", "postrm"))
			self._elog_keys = None

		super(MergeProcess, self)._unregister()
