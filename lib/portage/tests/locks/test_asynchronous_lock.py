# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import signal
import tempfile

try:
	import dummy_threading
except ImportError:
	dummy_threading = None

from portage import os
from portage import shutil
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from _emerge.AsynchronousLock import AsynchronousLock

class AsynchronousLockTestCase(TestCase):

	def _testAsynchronousLock(self):
		scheduler = global_event_loop()
		tempdir = tempfile.mkdtemp()
		try:
			path = os.path.join(tempdir, 'lock_me')
			for force_async in (True, False):
				for force_dummy in ((False,) if dummy_threading is None
					else (True, False)):
					async_lock = AsynchronousLock(path=path,
						scheduler=scheduler, _force_async=force_async,
						_force_thread=True,
						_force_dummy=force_dummy)
					async_lock.start()
					self.assertEqual(async_lock.wait(), os.EX_OK)
					self.assertEqual(async_lock.returncode, os.EX_OK)
					scheduler.run_until_complete(async_lock.async_unlock())

				async_lock = AsynchronousLock(path=path,
					scheduler=scheduler, _force_async=force_async,
					_force_process=True)
				async_lock.start()
				self.assertEqual(async_lock.wait(), os.EX_OK)
				self.assertEqual(async_lock.returncode, os.EX_OK)
				scheduler.run_until_complete(async_lock.async_unlock())
		finally:
			shutil.rmtree(tempdir)

	def testAsynchronousLock(self):
		self._testAsynchronousLock()

	def testAsynchronousLockHardlink(self):
		prev_state = os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
		os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = "1"
		try:
			self._testAsynchronousLock()
		finally:
			os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
			if prev_state is not None:
				os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = prev_state

	def _testAsynchronousLockWait(self):
		scheduler = global_event_loop()
		tempdir = tempfile.mkdtemp()
		try:
			path = os.path.join(tempdir, 'lock_me')
			lock1 = AsynchronousLock(path=path, scheduler=scheduler)
			lock1.start()
			self.assertEqual(lock1.wait(), os.EX_OK)
			self.assertEqual(lock1.returncode, os.EX_OK)

			# lock2 requires _force_async=True since the portage.locks
			# module is not designed to work as intended here if the
			# same process tries to lock the same file more than
			# one time concurrently.
			lock2 = AsynchronousLock(path=path, scheduler=scheduler,
				_force_async=True, _force_process=True)
			lock2.start()
			# lock2 should be waiting for lock1 to release
			self.assertEqual(lock2.poll(), None)
			self.assertEqual(lock2.returncode, None)

			scheduler.run_until_complete(lock1.async_unlock())
			self.assertEqual(lock2.wait(), os.EX_OK)
			self.assertEqual(lock2.returncode, os.EX_OK)
			scheduler.run_until_complete(lock2.async_unlock())
		finally:
			shutil.rmtree(tempdir)

	def testAsynchronousLockWait(self):
		self._testAsynchronousLockWait()

	def testAsynchronousLockWaitHardlink(self):
		prev_state = os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
		os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = "1"
		try:
			self._testAsynchronousLockWait()
		finally:
			os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
			if prev_state is not None:
				os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = prev_state

	def _testAsynchronousLockWaitCancel(self):
		scheduler = global_event_loop()
		tempdir = tempfile.mkdtemp()
		try:
			path = os.path.join(tempdir, 'lock_me')
			lock1 = AsynchronousLock(path=path, scheduler=scheduler)
			lock1.start()
			self.assertEqual(lock1.wait(), os.EX_OK)
			self.assertEqual(lock1.returncode, os.EX_OK)
			lock2 = AsynchronousLock(path=path, scheduler=scheduler,
				_force_async=True, _force_process=True)
			lock2.start()
			# lock2 should be waiting for lock1 to release
			self.assertEqual(lock2.poll(), None)
			self.assertEqual(lock2.returncode, None)

			# Cancel lock2 and then check wait() and returncode results.
			lock2.cancel()
			self.assertEqual(lock2.wait() == os.EX_OK, False)
			self.assertEqual(lock2.returncode == os.EX_OK, False)
			self.assertEqual(lock2.returncode is None, False)
			scheduler.run_until_complete(lock1.async_unlock())
		finally:
			shutil.rmtree(tempdir)

	def testAsynchronousLockWaitCancel(self):
		self._testAsynchronousLockWaitCancel()

	def testAsynchronousLockWaitCancelHardlink(self):
		prev_state = os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
		os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = "1"
		try:
			self._testAsynchronousLockWaitCancel()
		finally:
			os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
			if prev_state is not None:
				os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = prev_state

	def _testAsynchronousLockWaitKill(self):
		scheduler = global_event_loop()
		tempdir = tempfile.mkdtemp()
		try:
			path = os.path.join(tempdir, 'lock_me')
			lock1 = AsynchronousLock(path=path, scheduler=scheduler)
			lock1.start()
			self.assertEqual(lock1.wait(), os.EX_OK)
			self.assertEqual(lock1.returncode, os.EX_OK)
			lock2 = AsynchronousLock(path=path, scheduler=scheduler,
				_force_async=True, _force_process=True)
			lock2.start()
			# lock2 should be waiting for lock1 to release
			self.assertEqual(lock2.poll(), None)
			self.assertEqual(lock2.returncode, None)

			# Kill lock2's process and then check wait() and
			# returncode results. This is intended to simulate
			# a SIGINT sent via the controlling tty.
			self.assertEqual(lock2._imp is not None, True)
			self.assertEqual(lock2._imp._proc is not None, True)
			self.assertEqual(lock2._imp._proc.pid is not None, True)
			lock2._imp._kill_test = True
			os.kill(lock2._imp._proc.pid, signal.SIGTERM)
			self.assertEqual(lock2.wait() == os.EX_OK, False)
			self.assertEqual(lock2.returncode == os.EX_OK, False)
			self.assertEqual(lock2.returncode is None, False)
			scheduler.run_until_complete(lock1.async_unlock())
		finally:
			shutil.rmtree(tempdir)

	def testAsynchronousLockWaitKill(self):
		self._testAsynchronousLockWaitKill()

	def testAsynchronousLockWaitKillHardlink(self):
		prev_state = os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
		os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = "1"
		try:
			self._testAsynchronousLockWaitKill()
		finally:
			os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
			if prev_state is not None:
				os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = prev_state
