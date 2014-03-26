# Copyright 2010-2012 Gentoo Foundation
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
from portage.util._async.ForkProcess import ForkProcess
from portage.util._async.TaskScheduler import TaskScheduler
from portage.util._eventloop.global_event_loop import global_event_loop
from _emerge.SpawnProcess import SpawnProcess
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.EbuildIpcDaemon import EbuildIpcDaemon

class SleepProcess(ForkProcess):
	"""
	Emulate the sleep command, in order to ensure a consistent
	return code when it is killed by SIGTERM (see bug #437180).
	"""
	__slots__ = ('seconds',)
	def _run(self):
		time.sleep(self.seconds)

class IpcDaemonTestCase(TestCase):

	_SCHEDULE_TIMEOUT = 40000 # 40 seconds

	def testIpcDaemon(self):
		event_loop = global_event_loop()
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

			build_dir = EbuildBuildDir(
				scheduler=event_loop,
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
					output_fifo=output_fifo)
				proc = SpawnProcess(
					args=[BASH_BINARY, "-c",
					'"$PORTAGE_BIN_PATH"/ebuild-ipc exit %d' % exitcode],
					env=env)
				task_scheduler = TaskScheduler(iter([daemon, proc]),
					max_jobs=2, event_loop=event_loop)

				self.received_command = False
				def exit_command_callback():
					self.received_command = True
					task_scheduler.cancel()

				exit_command.reply_hook = exit_command_callback
				start_time = time.time()
				self._run(event_loop, task_scheduler, self._SCHEDULE_TIMEOUT)

				hardlock_cleanup(env['PORTAGE_BUILDDIR'],
					remove_all_locks=True)

				self.assertEqual(self.received_command, True,
					"command not received after %d seconds" % \
					(time.time() - start_time,))
				self.assertEqual(proc.isAlive(), False)
				self.assertEqual(daemon.isAlive(), False)
				self.assertEqual(exit_command.exitcode, exitcode)

			# Intentionally short timeout test for EventLoop/AsyncScheduler.
			# Use a ridiculously long sleep_time_s in case the user's
			# system is heavily loaded (see bug #436334).
			sleep_time_s = 600     #600.000 seconds
			short_timeout_ms = 10  #  0.010 seconds

			for i in range(3):
				exit_command = ExitCommand()
				commands = {'exit' : exit_command}
				daemon = EbuildIpcDaemon(commands=commands,
					input_fifo=input_fifo,
					output_fifo=output_fifo)
				proc = SleepProcess(seconds=sleep_time_s)
				task_scheduler = TaskScheduler(iter([daemon, proc]),
					max_jobs=2, event_loop=event_loop)

				self.received_command = False
				def exit_command_callback():
					self.received_command = True
					task_scheduler.cancel()

				exit_command.reply_hook = exit_command_callback
				start_time = time.time()
				self._run(event_loop, task_scheduler, short_timeout_ms)

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

	def _timeout_callback(self):
		self._timed_out = True

	def _run(self, event_loop, task_scheduler, timeout):
		self._timed_out = False
		timeout_id = event_loop.timeout_add(timeout, self._timeout_callback)

		try:
			task_scheduler.start()
			while not self._timed_out and task_scheduler.poll() is None:
				event_loop.iteration()
			if self._timed_out:
				task_scheduler.cancel()
			task_scheduler.wait()
		finally:
			event_loop.source_remove(timeout_id)
