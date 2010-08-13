# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import shutil
import tempfile
from portage import os
from portage.tests import TestCase
from portage.const import PORTAGE_BIN_PATH
from portage.const import PORTAGE_PYM_PATH
from portage.const import BASH_BINARY
from _emerge.SpawnProcess import SpawnProcess
from _emerge.EbuildIpcDaemon import EbuildIpcDaemon
from _emerge.TaskScheduler import TaskScheduler

class ExitCommand(object):

	def __init__(self):
		self.callback = None
		self.exitcode = None

	def __call__(self, argv, send_reply):
		duplicate = False
		if self.exitcode is not None:
			# Ignore all but the first call, since if die is called
			# then we certainly want to honor that exitcode, even
			# the ebuild process manages to send a second exit
			# command.
			duplicate = True
		else:
			self.exitcode = int(argv[1])

		# (stdout, stderr, returncode)
		send_reply(('', '', 0))
		if not duplicate and self.callback is not None:
			self.callback()

class IpcDaemonTestCase(TestCase):

	def testIpcDaemon(self):
		tmpdir = tempfile.mkdtemp()
		try:
			env = {}
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
					daemon.cancel()
					proc.cancel()
				exit_command.callback = exit_command_callback
				task_scheduler.add(daemon)
				task_scheduler.add(proc)
				task_scheduler.run()
				self.assertEqual(exit_command.exitcode, exitcode)
		finally:
			shutil.rmtree(tmpdir)
