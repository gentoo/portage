# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import tempfile
import time
from portage import os
from portage import shutil
from portage import _python_interpreter
from portage.tests import TestCase
from portage.const import PORTAGE_BIN_PATH
from portage.const import PORTAGE_PYM_PATH
from portage.const import BASH_BINARY
from portage.locks import hardlock_cleanup
from portage.package.ebuild._ipc.ExitCommand import ExitCommand
from portage.util import ensure_dirs
from _emerge.SpawnProcess import SpawnProcess
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.EbuildIpcDaemon import EbuildIpcDaemon
from _emerge.TaskScheduler import TaskScheduler

class IpcDaemonTestCase(TestCase):

	_SCHEDULE_TIMEOUT = 40000 # 40 seconds

	def testIpcDaemon(self):
		tmpdir = tempfile.mkdtemp()
		build_dir = None
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
			env['PORTAGE_BUILDDIR'] = os.path.join(tmpdir, 'cat', 'pkg-1')

			if "__PORTAGE_TEST_HARDLINK_LOCKS" in os.environ:
				env["__PORTAGE_TEST_HARDLINK_LOCKS"] = \
					os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"]

			task_scheduler = TaskScheduler(max_jobs=2)
			build_dir = EbuildBuildDir(
				scheduler=task_scheduler.sched_iface,
				settings=env)
			build_dir.lock()
			ensure_dirs(env['PORTAGE_BUILDDIR'])

			input_fifo = os.path.join(env['PORTAGE_BUILDDIR'], '.ipc_in')
			output_fifo = os.path.join(env['PORTAGE_BUILDDIR'], '.ipc_out')
			os.mkfifo(input_fifo)
			os.mkfifo(output_fifo)

			for exitcode in (0, 1, 2):
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

				self.received_command = False
				def exit_command_callback():
					self.received_command = True
					task_scheduler.clear()
					task_scheduler.wait()

				exit_command.reply_hook = exit_command_callback
				start_time = time.time()
				task_scheduler.add(daemon)
				task_scheduler.add(proc)
				task_scheduler.run(timeout=self._SCHEDULE_TIMEOUT)
				task_scheduler.clear()
				task_scheduler.wait()
				hardlock_cleanup(env['PORTAGE_BUILDDIR'],
					remove_all_locks=True)

				self.assertEqual(self.received_command, True,
					"command not received after %d seconds" % \
					(time.time() - start_time,))
				self.assertEqual(proc.isAlive(), False)
				self.assertEqual(daemon.isAlive(), False)
				self.assertEqual(exit_command.exitcode, exitcode)

			# Intentionally short timeout test for QueueScheduler.run()
			sleep_time_s = 10      # 10.000 seconds
			short_timeout_ms = 10  #  0.010 seconds

			for i in range(3):
				exit_command = ExitCommand()
				commands = {'exit' : exit_command}
				daemon = EbuildIpcDaemon(commands=commands,
					input_fifo=input_fifo,
					output_fifo=output_fifo,
					scheduler=task_scheduler.sched_iface)
				proc = SpawnProcess(
					args=[BASH_BINARY, "-c", 'exec sleep %d' % sleep_time_s],
					env=env, scheduler=task_scheduler.sched_iface)

				self.received_command = False
				def exit_command_callback():
					self.received_command = True
					task_scheduler.clear()
					task_scheduler.wait()

				exit_command.reply_hook = exit_command_callback
				start_time = time.time()
				task_scheduler.add(daemon)
				task_scheduler.add(proc)
				task_scheduler.run(timeout=short_timeout_ms)
				task_scheduler.clear()
				task_scheduler.wait()
				hardlock_cleanup(env['PORTAGE_BUILDDIR'],
					remove_all_locks=True)

				self.assertEqual(self.received_command, False,
					"command received after %d seconds" % \
					(time.time() - start_time,))
				self.assertEqual(proc.isAlive(), False)
				self.assertEqual(daemon.isAlive(), False)
				self.assertEqual(proc.returncode == os.EX_OK, False)

		finally:
			if build_dir is not None:
				build_dir.unlock()
			shutil.rmtree(tmpdir)
