# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
import signal
import sys
import traceback

import errno
import fcntl
import portage
from portage import os, _unicode_decode
from portage.dbapi.vartree import _get_syncfs
import portage.elog.messages
from portage.util._async.ForkProcess import ForkProcess

class MergeProcess(ForkProcess):
	"""
	Merge packages in a subprocess, so the Scheduler can run in the main
	thread while files are moved or copied asynchronously.
	"""

	__slots__ = ('mycat', 'mypkg', 'settings', 'treetype',
		'vartree', 'blockers', 'pkgloc', 'infloc', 'myebuild',
		'mydbapi', 'prev_mtimes', 'unmerge', '_elog_reader_fd', '_elog_reg_id',
		'_buf', '_elog_keys', '_locked_vdb')

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
		_get_syncfs()

		# Inherit stdin by default, so that the pdb SIGUSR1
		# handler is usable for the subprocess.
		if self.fd_pipes is None:
			self.fd_pipes = {}
		self.fd_pipes.setdefault(0, sys.stdin.fileno())

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

	def _elog_output_handler(self, fd, event):
		output = None
		if event & self.scheduler.IO_IN:
			try:
				output = os.read(fd, self._bufsize)
			except OSError as e:
				if e.errno not in (errno.EAGAIN, errno.EINTR):
					raise
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

		if event & self.scheduler.IO_HUP:
			self.scheduler.source_remove(self._elog_reg_id)
			self._elog_reg_id = None
			os.close(self._elog_reader_fd)
			self._elog_reader_fd = None
			return False

		return True

	def _spawn(self, args, fd_pipes, **kwargs):
		"""
		Fork a subprocess, apply local settings, and call
		dblink.merge(). TODO: Share code with ForkProcess.
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
		self._elog_reg_id = self.scheduler.io_add_watch(elog_reader_fd,
			self._registered_events, self._elog_output_handler)

		# If a concurrent emerge process tries to install a package
		# in the same SLOT as this one at the same time, there is an
		# extremely unlikely chance that the COUNTER values will not be
		# ordered correctly unless we lock the vdb here.
		# FEATURES=parallel-install skips this lock in order to
		# improve performance, and the risk is practically negligible.
		self._lock_vdb()
		counter = None
		if not self.unmerge:
			counter = self.vartree.dbapi.counter_tick()

		parent_pid = os.getpid()
		pid = None
		try:
			pid = os.fork()

			if pid != 0:
				if not isinstance(pid, int):
					raise AssertionError(
						"fork returned non-integer: %s" % (repr(pid),))

				os.close(elog_writer_fd)
				self._elog_reader_fd = elog_reader_fd
				self._buf = ""
				self._elog_keys = set()

				# invalidate relevant vardbapi caches
				if self.vartree.dbapi._categories is not None:
					self.vartree.dbapi._categories = None
				self.vartree.dbapi._pkgs_changed = True
				self.vartree.dbapi._clear_pkg_cache(mylink)

				portage.process.spawned_pids.append(pid)
				return [pid]

			os.close(elog_reader_fd)

			# Use default signal handlers in order to avoid problems
			# killing subprocesses as reported in bug #353239.
			signal.signal(signal.SIGINT, signal.SIG_DFL)
			signal.signal(signal.SIGTERM, signal.SIG_DFL)

			portage.locks._close_fds()
			# We don't exec, so use close_fds=False
			# (see _setup_pipes docstring).
			portage.process._setup_pipes(fd_pipes, close_fds=False)

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
			try:
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
			except SystemExit:
				raise
			except:
				traceback.print_exc()
			finally:
				os._exit(rval)

		finally:
			if pid == 0 or (pid is None and os.getpid() != parent_pid):
				# Call os._exit() from a finally block in order
				# to suppress any finally blocks from earlier
				# in the call stack (see bug #345289). This
				# finally block has to be setup before the fork
				# in order to avoid a race condition.
				os._exit(1)

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
		if self._elog_reg_id is not None:
			self.scheduler.source_remove(self._elog_reg_id)
			self._elog_reg_id = None
		if self._elog_reader_fd is not None:
			os.close(self._elog_reader_fd)
			self._elog_reader_fd = None
		if self._elog_keys is not None:
			for key in self._elog_keys:
				portage.elog.elog_process(key, self.settings,
					phasefilter=("prerm", "postrm"))
			self._elog_keys = None

		super(MergeProcess, self)._unregister()
