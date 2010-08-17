# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import shutil
import tempfile
from portage import os
from portage import _python_interpreter
from portage.tests import TestCase
from portage.const import PORTAGE_BIN_PATH
from portage.const import PORTAGE_PYM_PATH
from portage.const import BASH_BINARY
from portage.package.ebuild._ipc.ExitCommand import ExitCommand
from _emerge.SpawnProcess import SpawnProcess
from _emerge.EbuildIpcDaemon import EbuildIpcDaemon
from _emerge.TaskScheduler import TaskScheduler

class IpcDaemonTestCase(TestCase):

	def testIpcDaemon(self):
		tmpdir = tempfile.mkdtemp()
		try:
			env = {}

			# Pass along PORTAGE_USERNAME and PORTAGE_GRPNAME since they
			# need to be inherited by ebuild subprocesses.
			if 'PORTAGE_USERNAME' in os.environ:
				env['PORTAGE_USERNAME'] = os.environ['PORTAGE_USERNAME']
			if 'PORTAGE_GRPNAME' in os.environ:
				env['PORTAGE_GRPNAME'] = os.environ['PORTAGE_GRPNAME']

			env['PORTAGE_PYTHON'] = _python_interpreter
			env['PORTAGE_BIN_PATH'] = PORTAGE_BIN_PATH
			env['PORTAGE_PYM_PATH'] = PORTAGE_PYM_PATH
			env['PORTAGE_BUILDDIR'] = tmpdir

			input_fifo = os.path.join(tmpdir, '.ipc_in')
			output_fifo = os.path.join(tmpdir, '.ipc_out')
			os.mkfifo(input_fifo)
			os.mkfifo(output_fifo)
			for exitcode in (0, 1, 2):
				task_scheduler = TaskScheduler(max_jobs=2)
				exit_command = ExitCommand()
				commands = {'exit' : exit_command}
				daemon = EbuildIpcDaemon(commands=commands,
					input_fifo=input_fifo,
					output_fifo=output_fifo,
					scheduler=task_scheduler.sched_iface)
				proc = SpawnProcess(
					args=[BASH_BINARY, "-c",
					'"$PORTAGE_BIN_PATH"/ebuild-ipc exit %d' % exitcode],
					env=env, scheduler=task_scheduler.sched_iface)
				def exit_command_callback():
					proc.cancel()
					daemon.cancel()
				exit_command.reply_hook = exit_command_callback
				task_scheduler.add(daemon)
				task_scheduler.add(proc)
				task_scheduler.run()
				self.assertEqual(exit_command.exitcode, exitcode)
		finally:
			shutil.rmtree(tmpdir)
