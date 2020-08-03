# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import io
import platform
import stat
import subprocess
import tempfile
import textwrap
from _emerge.SpawnProcess import SpawnProcess
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.EbuildIpcDaemon import EbuildIpcDaemon
import portage
from portage.elog import messages as elog_messages
from portage.localization import _
from portage.package.ebuild._ipc.ExitCommand import ExitCommand
from portage.package.ebuild._ipc.QueryCommand import QueryCommand
from portage import os
from portage.util.futures import asyncio
from portage.util._pty import _create_pty_or_pipe
from portage.util import apply_secpass_permissions

portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.doebuild:_global_pid_phases',
)

class AbstractEbuildProcess(SpawnProcess):

	__slots__ = ('phase', 'settings',) + \
		('_build_dir', '_build_dir_unlock', '_ipc_daemon',
		'_exit_command', '_exit_timeout_id', '_start_future')

	_phases_without_builddir = ('clean', 'cleanrm', 'depend', 'help',)
	_phases_interactive_whitelist = ('config',)

	# Number of milliseconds to allow natural exit of the ebuild
	# process after it has called the exit command via IPC. It
	# doesn't hurt to be generous here since the scheduler
	# continues to process events during this period, and it can
	# return long before the timeout expires.
	_exit_timeout = 10 # seconds

	# The EbuildIpcDaemon support is well tested, but this variable
	# is left so we can temporarily disable it if any issues arise.
	_enable_ipc_daemon = True

	def __init__(self, **kwargs):
		SpawnProcess.__init__(self, **kwargs)
		if self.phase is None:
			phase = self.settings.get("EBUILD_PHASE")
			if not phase:
				phase = 'other'
			self.phase = phase

	def _start(self):

		need_builddir = self.phase not in self._phases_without_builddir

		# This can happen if the pre-clean phase triggers
		# die_hooks for some reason, and PORTAGE_BUILDDIR
		# doesn't exist yet.
		if need_builddir and \
			not os.path.isdir(self.settings['PORTAGE_BUILDDIR']):
			msg = _("The ebuild phase '%s' has been aborted "
			"since PORTAGE_BUILDDIR does not exist: '%s'") % \
			(self.phase, self.settings['PORTAGE_BUILDDIR'])
			self._eerror(textwrap.wrap(msg, 72))
			self.returncode = 1
			self._async_wait()
			return

		# Check if the cgroup hierarchy is in place. If it's not, mount it.
		if (os.geteuid() == 0 and platform.system() == 'Linux'
				and 'cgroup' in self.settings.features
				and self.phase not in _global_pid_phases):
			cgroup_root = '/sys/fs/cgroup'
			cgroup_portage = os.path.join(cgroup_root, 'portage')

			try:
				# cgroup tmpfs
				if not os.path.ismount(cgroup_root):
					# we expect /sys/fs to be there already
					if not os.path.isdir(cgroup_root):
						os.mkdir(cgroup_root, 0o755)
					subprocess.check_call(['mount', '-t', 'tmpfs',
						'-o', 'rw,nosuid,nodev,noexec,mode=0755',
						'tmpfs', cgroup_root])

				# portage subsystem
				if not os.path.ismount(cgroup_portage):
					if not os.path.isdir(cgroup_portage):
						os.mkdir(cgroup_portage, 0o755)
					subprocess.check_call(['mount', '-t', 'cgroup',
						'-o', 'rw,nosuid,nodev,noexec,none,name=portage',
						'tmpfs', cgroup_portage])
					with open(os.path.join(
						cgroup_portage, 'release_agent'), 'w') as f:
						f.write(os.path.join(self.settings['PORTAGE_BIN_PATH'],
							'cgroup-release-agent'))
					with open(os.path.join(
						cgroup_portage, 'notify_on_release'), 'w') as f:
						f.write('1')
				else:
					# Update release_agent if it no longer exists, because
					# it refers to a temporary path when portage is updating
					# itself.
					release_agent = os.path.join(
						cgroup_portage, 'release_agent')
					try:
						with open(release_agent) as f:
							release_agent_path = f.readline().rstrip('\n')
					except EnvironmentError:
						release_agent_path = None

					if (release_agent_path is None or
						not os.path.exists(release_agent_path)):
						with open(release_agent, 'w') as f:
							f.write(os.path.join(
								self.settings['PORTAGE_BIN_PATH'],
								'cgroup-release-agent'))

				cgroup_path = tempfile.mkdtemp(dir=cgroup_portage,
					prefix='%s:%s.' % (self.settings["CATEGORY"],
					self.settings["PF"]))
			except (subprocess.CalledProcessError, OSError):
				pass
			else:
				self.cgroup = cgroup_path

		if self.background:
			# Automatically prevent color codes from showing up in logs,
			# since we're not displaying to a terminal anyway.
			self.settings['NOCOLOR'] = 'true'

		start_ipc_daemon = False
		if self._enable_ipc_daemon:
			self.settings.pop('PORTAGE_EBUILD_EXIT_FILE', None)
			if self.phase not in self._phases_without_builddir:
				start_ipc_daemon = True
				if 'PORTAGE_BUILDDIR_LOCKED' not in self.settings:
					self._build_dir = EbuildBuildDir(
						scheduler=self.scheduler, settings=self.settings)
					self._start_future = self._build_dir.async_lock()
					self._start_future.add_done_callback(
						functools.partial(self._start_post_builddir_lock,
						start_ipc_daemon=start_ipc_daemon))
					return
			else:
				self.settings.pop('PORTAGE_IPC_DAEMON', None)
		else:
			# Since the IPC daemon is disabled, use a simple tempfile based
			# approach to detect unexpected exit like in bug #190128.
			self.settings.pop('PORTAGE_IPC_DAEMON', None)
			if self.phase not in self._phases_without_builddir:
				exit_file = os.path.join(
					self.settings['PORTAGE_BUILDDIR'],
					'.exit_status')
				self.settings['PORTAGE_EBUILD_EXIT_FILE'] = exit_file
				try:
					os.unlink(exit_file)
				except OSError:
					if os.path.exists(exit_file):
						# make sure it doesn't exist
						raise
			else:
				self.settings.pop('PORTAGE_EBUILD_EXIT_FILE', None)

		self._start_post_builddir_lock(start_ipc_daemon=start_ipc_daemon)

	def _start_post_builddir_lock(self, lock_future=None, start_ipc_daemon=False):
		if lock_future is not None:
			if lock_future is not self._start_future:
				raise AssertionError('lock_future is not self._start_future')
			self._start_future = None
			if lock_future.cancelled():
				self._build_dir = None
				self.cancelled = True
				self._was_cancelled()
				self._async_wait()
				return

			lock_future.result()

		if start_ipc_daemon:
			self.settings['PORTAGE_IPC_DAEMON'] = "1"
			self._start_ipc_daemon()

		if self.fd_pipes is None:
			self.fd_pipes = {}
		null_fd = None
		if 0 not in self.fd_pipes and \
			self.phase not in self._phases_interactive_whitelist and \
			"interactive" not in self.settings.get("PROPERTIES", "").split():
			null_fd = os.open('/dev/null', os.O_RDONLY)
			self.fd_pipes[0] = null_fd

		self.log_filter_file = self.settings.get('PORTAGE_LOG_FILTER_FILE_CMD')
		try:
			SpawnProcess._start(self)
		finally:
			if null_fd is not None:
				os.close(null_fd)

	def _init_ipc_fifos(self):

		input_fifo = os.path.join(
			self.settings['PORTAGE_BUILDDIR'], '.ipc_in')
		output_fifo = os.path.join(
			self.settings['PORTAGE_BUILDDIR'], '.ipc_out')

		for p in (input_fifo, output_fifo):

			st = None
			try:
				st = os.lstat(p)
			except OSError:
				os.mkfifo(p)
			else:
				if not stat.S_ISFIFO(st.st_mode):
					st = None
					try:
						os.unlink(p)
					except OSError:
						pass
					os.mkfifo(p)

			apply_secpass_permissions(p,
				uid=os.getuid(),
				gid=portage.data.portage_gid,
				mode=0o770, stat_cached=st)

		return (input_fifo, output_fifo)

	def _start_ipc_daemon(self):
		self._exit_command = ExitCommand()
		self._exit_command.reply_hook = self._exit_command_callback
		query_command = QueryCommand(self.settings, self.phase)
		commands = {
			'available_eclasses'  : query_command,
			'best_version'        : query_command,
			'eclass_path'         : query_command,
			'exit'                : self._exit_command,
			'has_version'         : query_command,
			'license_path'        : query_command,
			'master_repositories' : query_command,
			'repository_path'     : query_command,
		}
		input_fifo, output_fifo = self._init_ipc_fifos()
		self._ipc_daemon = EbuildIpcDaemon(commands=commands,
			input_fifo=input_fifo,
			output_fifo=output_fifo,
			scheduler=self.scheduler)
		self._ipc_daemon.start()

	def _exit_command_callback(self):
		if self._registered:
			# Let the process exit naturally, if possible.
			self._exit_timeout_id = \
				self.scheduler.call_later(self._exit_timeout,
				self._exit_command_timeout_cb)

	def _exit_command_timeout_cb(self):
		if self._registered:
			# If it doesn't exit naturally in a reasonable amount
			# of time, kill it (solves bug #278895). We try to avoid
			# this when possible since it makes sandbox complain about
			# being killed by a signal.
			self.cancel()
			self._exit_timeout_id = \
				self.scheduler.call_later(self._cancel_timeout,
					self._cancel_timeout_cb)
		else:
			self._exit_timeout_id = None

	def _cancel_timeout_cb(self):
		self._exit_timeout_id = None
		self._async_waitpid()

	def _orphan_process_warn(self):
		phase = self.phase

		msg = _("The ebuild phase '%s' with pid %s appears "
		"to have left an orphan process running in the "
		"background.") % (phase, self.pid)

		self._eerror(textwrap.wrap(msg, 72))

	def _pipe(self, fd_pipes):
		stdout_pipe = None
		if not self.background:
			stdout_pipe = fd_pipes.get(1)
		got_pty, master_fd, slave_fd = \
			_create_pty_or_pipe(copy_term_size=stdout_pipe)
		return (master_fd, slave_fd)

	def _can_log(self, slave_fd):
		# With sesandbox, logging works through a pty but not through a
		# normal pipe. So, disable logging if ptys are broken.
		# See Bug #162404.
		# TODO: Add support for logging via named pipe (fifo) with
		# sesandbox, since EbuildIpcDaemon uses a fifo and it's known
		# to be compatible with sesandbox.
		return not ('sesandbox' in self.settings.features \
			and self.settings.selinux_enabled()) or os.isatty(slave_fd)

	def _killed_by_signal(self, signum):
		msg = _("The ebuild phase '%s' has been "
		"killed by signal %s.") % (self.phase, signum)
		self._eerror(textwrap.wrap(msg, 72))

	def _unexpected_exit(self):

		phase = self.phase

		msg = _("The ebuild phase '%s' has exited "
		"unexpectedly. This type of behavior "
		"is known to be triggered "
		"by things such as failed variable "
		"assignments (bug #190128) or bad substitution "
		"errors (bug #200313). Normally, before exiting, bash should "
		"have displayed an error message above. If bash did not "
		"produce an error message above, it's possible "
		"that the ebuild has called `exit` when it "
		"should have called `die` instead. This behavior may also "
		"be triggered by a corrupt bash binary or a hardware "
		"problem such as memory or cpu malfunction. If the problem is not "
		"reproducible or it appears to occur randomly, then it is likely "
		"to be triggered by a hardware problem. "
		"If you suspect a hardware problem then you should "
		"try some basic hardware diagnostics such as memtest. "
		"Please do not report this as a bug unless it is consistently "
		"reproducible and you are sure that your bash binary and hardware "
		"are functioning properly.") % phase

		self._eerror(textwrap.wrap(msg, 72))

	def _eerror(self, lines):
		self._elog('eerror', lines)

	def _elog(self, elog_funcname, lines):
		out = io.StringIO()
		phase = self.phase
		elog_func = getattr(elog_messages, elog_funcname)
		global_havecolor = portage.output.havecolor
		try:
			portage.output.havecolor = \
				self.settings.get('NOCOLOR', 'false').lower() in ('no', 'false')
			for line in lines:
				elog_func(line, phase=phase, key=self.settings.mycpv, out=out)
		finally:
			portage.output.havecolor = global_havecolor
		msg = out.getvalue()
		if msg:
			log_path = None
			if self.settings.get("PORTAGE_BACKGROUND") != "subprocess":
				log_path = self.settings.get("PORTAGE_LOG_FILE")
			self.scheduler.output(msg, log_path=log_path)

	def _async_waitpid_cb(self, *args, **kwargs):
		"""
		Override _async_waitpid_cb to perform cleanup that is
		not necessarily idempotent.
		"""
		SpawnProcess._async_waitpid_cb(self, *args, **kwargs)

		if self._exit_timeout_id is not None:
			self._exit_timeout_id.cancel()
			self._exit_timeout_id = None

		if self._ipc_daemon is not None:
			self._ipc_daemon.cancel()
			if self._exit_command.exitcode is not None:
				self.returncode = self._exit_command.exitcode
			else:
				if self.returncode < 0:
					if not self.cancelled:
						self._killed_by_signal(-self.returncode)
				else:
					self.returncode = 1
					if not self.cancelled:
						self._unexpected_exit()

		elif not self.cancelled:
			exit_file = self.settings.get('PORTAGE_EBUILD_EXIT_FILE')
			if exit_file and not os.path.exists(exit_file):
				if self.returncode < 0:
					if not self.cancelled:
						self._killed_by_signal(-self.returncode)
				else:
					self.returncode = 1
					if not self.cancelled:
						self._unexpected_exit()

	def _async_wait(self):
		"""
		Override _async_wait to asynchronously unlock self._build_dir
		when necessary.
		"""
		if self._build_dir is None:
			SpawnProcess._async_wait(self)
		elif self._build_dir_unlock is None:
			if self.returncode is None:
				raise asyncio.InvalidStateError('Result is not ready for %s' % (self,))
			self._async_unlock_builddir(returncode=self.returncode)

	def _async_unlock_builddir(self, returncode=None):
		"""
		Release the lock asynchronously, and if a returncode parameter
		is given then set self.returncode and notify exit listeners.
		"""
		if self._build_dir_unlock is not None:
			raise AssertionError('unlock already in progress')
		if returncode is not None:
			# The returncode will be set after unlock is complete.
			self.returncode = None
		self._build_dir_unlock = self._build_dir.async_unlock()
		# Unlock only once.
		self._build_dir = None
		self._build_dir_unlock.add_done_callback(
			functools.partial(self._unlock_builddir_exit, returncode=returncode))

	def _unlock_builddir_exit(self, unlock_future, returncode=None):
		# Normally, async_unlock should not raise an exception here.
		unlock_future.cancelled() or unlock_future.result()
		if returncode is not None:
			if unlock_future.cancelled():
				self.cancelled = True
				self._was_cancelled()
			else:
				self.returncode = returncode
			SpawnProcess._async_wait(self)
