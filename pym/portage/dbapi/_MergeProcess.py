# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import signal
import traceback

import errno
import fcntl
import portage
from portage import os, StringIO, _unicode_decode
import portage.elog.messages
from _emerge.PollConstants import PollConstants
from _emerge.SpawnProcess import SpawnProcess

class MergeProcess(SpawnProcess):
	"""
	Merge packages in a subprocess, so the Scheduler can run in the main
	thread while files are moved or copied asynchronously.
	"""

	__slots__ = ('dblink', 'mycat', 'mypkg', 'settings', 'treetype',
		'vartree', 'scheduler', 'blockers', 'pkgloc', 'infloc', 'myebuild',
		'mydbapi', 'prev_mtimes', '_elog_reader_fd', '_elog_reg_id',
		'_buf', '_elog_keys')

	def _elog_output_handler(self, fd, event):
		output = None
		if event & PollConstants.POLLIN:
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
				out = StringIO()
				for line in lines:
					funcname, phase, key, msg = line.split(' ', 3)
					self._elog_keys.add(key)
					reporter = getattr(portage.elog.messages, funcname)
					reporter(msg, phase=phase, key=key, out=out)

	def _spawn(self, args, fd_pipes, **kwargs):
		"""
		Fork a subprocess, apply local settings, and call
		dblink.merge().
		"""

		files = self._files
		elog_reader_fd, elog_writer_fd = os.pipe()
		fcntl.fcntl(elog_reader_fd, fcntl.F_SETFL,
			fcntl.fcntl(elog_reader_fd, fcntl.F_GETFL) | os.O_NONBLOCK)
		mylink = self.dblink(self.mycat, self.mypkg, settings=self.settings,
			treetype=self.treetype, vartree=self.vartree,
			blockers=self.blockers, scheduler=self.scheduler,
			pipe=elog_writer_fd)
		fd_pipes[elog_writer_fd] = elog_writer_fd
		self._elog_reg_id = self.scheduler.register(elog_reader_fd,
			self._registered_events, self._elog_output_handler)

		pid = os.fork()
		if pid != 0:
			os.close(elog_writer_fd)
			self._elog_reader_fd = elog_reader_fd
			self._buf = ""
			self._elog_keys = set()
			self.vartree.dbapi._pkgs_changed = True
			portage.process.spawned_pids.append(pid)
			return [pid]

		os.close(elog_reader_fd)
		portage.process._setup_pipes(fd_pipes)

		# Use default signal handlers since the ones inherited
		# from the parent process are irrelevant here.
		signal.signal(signal.SIGINT, signal.SIG_DFL)
		signal.signal(signal.SIGTERM, signal.SIG_DFL)

		portage.output.havecolor = self.settings.get('NOCOLOR') \
			not in ('yes', 'true')

		# In this subprocess we want mylink._display_merge() to use
		# stdout/stderr directly since they are pipes. This behavior
		# is triggered when mylink._scheduler is None.
		mylink._scheduler = None

		# In this subprocess we don't want PORTAGE_BACKGROUND to
		# suppress stdout/stderr output since they are pipes. We
		# also don't want to open PORTAGE_LOG_FILE, since it will
		# already be opened by the parent process, so we set the
		# "subprocess" value for use in conditional logging code
		# involving PORTAGE_LOG_FILE.
		if self.settings.get("PORTAGE_BACKGROUND") == "1":
			# unmerge phases have separate logs
			self.settings["PORTAGE_BACKGROUND_UNMERGE"] = "1"
			self.settings.backup_changes("PORTAGE_BACKGROUND_UNMERGE")
		self.settings["PORTAGE_BACKGROUND"] = "subprocess"
		self.settings.backup_changes("PORTAGE_BACKGROUND")

		rval = 1
		try:
			rval = mylink.merge(self.pkgloc, self.infloc,
				myebuild=self.myebuild, mydbapi=self.mydbapi,
				prev_mtimes=self.prev_mtimes)
		except SystemExit:
			raise
		except:
			traceback.print_exc()
		finally:
			# Call os._exit() from finally block, in order to suppress any
			# finally blocks from earlier in the call stack. See bug #345289.
			os._exit(rval)

	def _unregister(self):
		"""
		Unregister from the scheduler and close open files.
		"""
		if self._elog_reg_id is not None:
			self.scheduler.unregister(self._elog_reg_id)
			self._elog_reg_id = None
		if self._elog_reader_fd:
			os.close(self._elog_reader_fd)
			self._elog_reader_fd = None
		if self._elog_keys is not None:
			for key in self._elog_keys:
				portage.elog.elog_process(key, self.settings,
					phasefilter=("prerm", "postrm"))
			self._elog_keys = None

		super(MergeProcess, self)._unregister()
