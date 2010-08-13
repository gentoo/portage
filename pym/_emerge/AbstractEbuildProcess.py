# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import textwrap
from _emerge.SpawnProcess import SpawnProcess
from _emerge.EbuildIpcDaemon import EbuildIpcDaemon
from portage.elog.messages import eerror
from portage.localization import _
from portage.package.ebuild._ipc.ExitCommand import ExitCommand
from portage import os
from portage.util._pty import _create_pty_or_pipe

class AbstractEbuildProcess(SpawnProcess):

	__slots__ = ('settings',) + \
		('_ipc_daemon', '_exit_command',)
	_phases_without_builddir = ('clean', 'cleanrm', 'depend', 'help',)

	def _get_phase(self):
		phase = getattr(self, 'phase', None)
		if not phase:
			phase = self.settings.get("EBUILD_PHASE")
			if not phase:
				phase = 'other'
		return phase

	def _start(self):

		if self._get_phase() not in self._phases_without_builddir:
			envs = [self.settings]
			if self.env is not None:
				envs.append(self.env)
			for env in envs:
				env['PORTAGE_IPC_DAEMON'] = "1"
			self._exit_command = ExitCommand()
			self._exit_command.reply_hook = self._exit_command_callback
			input_fifo = os.path.join(
				self.settings['PORTAGE_BUILDDIR'], '.ipc_in')
			output_fifo = os.path.join(
				self.settings['PORTAGE_BUILDDIR'], '.ipc_out')
			commands = {'exit' : self._exit_command}
			self._ipc_daemon = EbuildIpcDaemon(commands=commands,
				input_fifo=input_fifo,
				output_fifo=output_fifo,
				scheduler=self.scheduler)
			self._ipc_daemon.start()

		SpawnProcess._start(self)

	def _exit_command_callback(self):
		if self._registered:
			# Let the process exit naturally, if possible. This
			# doesn't really do any harm since it can return
			# long before the timeout expires.
			self.scheduler.schedule(self._reg_id, timeout=1000)
			if self._registered:
				# If it doesn't exit naturally in a reasonable amount
				# of time, kill it (solves bug #278895). We try to avoid
				# this when possible since it makes sandbox complain about
				# being killed by a signal.
				self.cancel()

	def _zombie(self):
		phase = self._get_phase()

		msg = _("The ebuild phase '%s' appears "
		"to have left a zombie process with "
		"pid %d.") % (phase, self.pid)

		for l in textwrap.wrap(msg, 72):
			eerror(l, phase=phase, key=self.settings.mycpv)

	def _pipe(self, fd_pipes):
		stdout_pipe = fd_pipes.get(1)
		got_pty, master_fd, slave_fd = \
			_create_pty_or_pipe(copy_term_size=stdout_pipe)
		return (master_fd, slave_fd)

	def _can_log(self, slave_fd):
		# With sesandbox, logging works through a pty but not through a
		# normal pipe. So, disable logging if ptys are broken.
		# See Bug #162404.
		return not ('sesandbox' in self.settings.features \
			and self.settings.selinux_enabled()) or os.isatty(slave_fd)

	def _unexpected_exit(self):

		phase = self._get_phase()

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

		for l in textwrap.wrap(msg, 72):
			eerror(l, phase=phase, key=self.settings.mycpv)

	def _set_returncode(self, wait_retval):
		SpawnProcess._set_returncode(self, wait_retval)

		if self._ipc_daemon is not None:
			self._ipc_daemon.cancel()
			if self._exit_command.exitcode is not None:
				self.returncode = self._exit_command.exitcode
			else:
				self.returncode = 1
				self._unexpected_exit()
