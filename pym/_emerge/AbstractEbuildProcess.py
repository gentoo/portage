# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import codecs
import textwrap
from _emerge.SpawnProcess import SpawnProcess
from _emerge.EbuildIpcDaemon import EbuildIpcDaemon
from portage.elog.messages import eerror
from portage.localization import _
from portage.package.ebuild._ipc.ExitCommand import ExitCommand
from portage.package.ebuild._ipc.QueryCommand import QueryCommand
from portage import os
from portage import StringIO
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.util._pty import _create_pty_or_pipe
from portage.util import writemsg_stdout

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
			self.settings['PORTAGE_IPC_DAEMON'] = "1"
			self._exit_command = ExitCommand()
			self._exit_command.reply_hook = self._exit_command_callback
			input_fifo = os.path.join(
				self.settings['PORTAGE_BUILDDIR'], '.ipc_in')
			output_fifo = os.path.join(
				self.settings['PORTAGE_BUILDDIR'], '.ipc_out')
			query_command = QueryCommand(self.settings)
			commands = {
				'best_version' : query_command,
				'exit'         : self._exit_command,
				'has_version'  : query_command,
			}
			self._ipc_daemon = EbuildIpcDaemon(commands=commands,
				input_fifo=input_fifo,
				output_fifo=output_fifo,
				scheduler=self.scheduler)
			self._ipc_daemon.start()
		else:
			self.settings.pop('PORTAGE_IPC_DAEMON', None)

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

	def _orphan_process_warn(self):
		phase = self._get_phase()

		msg = _("The ebuild phase '%s' with pid %s appears "
		"to have left an orphan process running in the "
		"background.") % (phase, self.pid)

		self._eerror(textwrap.wrap(msg, 72))

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

		self._eerror(textwrap.wrap(msg, 72))

	def _eerror(self, lines):
		out = StringIO()
		phase = self._get_phase()
		for line in lines:
			eerror(line, phase=phase, key=self.settings.mycpv, out=out)
		logfile = self.logfile
		if logfile is None:
			logfile = self.settings.get("PORTAGE_LOG_FILE")
		msg = _unicode_decode(out.getvalue(),
			encoding=_encodings['content'], errors='replace')
		if msg:
			if not self.background:
				writemsg_stdout(msg, noiselevel=-1)
			if logfile is not None:
				log_file = codecs.open(_unicode_encode(logfile,
					encoding=_encodings['fs'], errors='strict'),
					mode='a', encoding=_encodings['content'],
					errors='backslashreplace')
				log_file.write(msg)
				log_file.close()

	def _set_returncode(self, wait_retval):
		SpawnProcess._set_returncode(self, wait_retval)

		if self._ipc_daemon is not None:
			self._ipc_daemon.cancel()
			if self._exit_command.exitcode is not None:
				self.returncode = self._exit_command.exitcode
			else:
				self.returncode = 1
				self._unexpected_exit()
