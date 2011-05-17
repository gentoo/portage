# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import shutil
import tempfile

from portage import os
from portage.tests import TestCase
from _emerge.AsynchronousLock import AsynchronousLock
from _emerge.PollScheduler import PollScheduler

class AsynchronousLockTestCase(TestCase):

	def testAsynchronousLock(self):
		scheduler = PollScheduler().sched_iface
		tempdir = tempfile.mkdtemp()
		try:
			path = os.path.join(tempdir, 'lock_me')
			for force_async in (True, False):
				for force_dummy in (True, False):
					async_lock = AsynchronousLock(path=path,
						scheduler=scheduler, _force_async=force_async,
						_force_thread=True,
						_force_dummy=force_dummy)
					async_lock.start()
					async_lock.wait()
					async_lock.unlock()
					self.assertEqual(async_lock.returncode, os.EX_OK)

				async_lock = AsynchronousLock(path=path,
					scheduler=scheduler, _force_async=force_async,
					_force_process=True)
				async_lock.start()
				async_lock.wait()
				async_lock.unlock()
				self.assertEqual(async_lock.returncode, os.EX_OK)

		finally:
			shutil.rmtree(tempdir)

	def testAsynchronousLockWait(self):
		scheduler = PollScheduler().sched_iface
		tempdir = tempfile.mkdtemp()
		try:
			path = os.path.join(tempdir, 'lock_me')
			lock1 = AsynchronousLock(path=path, scheduler=scheduler)
			lock1.start()
			self.assertEqual(lock1.wait(), os.EX_OK)

			# lock2 requires _force_async=True since the portage.locks
			# module is not designed to work as intended here if the
			# same process tries to lock the same file more than
			# one time concurrently.
			lock2 = AsynchronousLock(path=path, scheduler=scheduler,
				_force_async=True, _force_process=True)
			lock2.start()
			# lock2 should we waiting for lock1 to release
			self.assertEqual(lock2.returncode, None)

			lock1.unlock()
			self.assertEqual(lock2.wait(), os.EX_OK)
			lock2.unlock()
		finally:
			shutil.rmtree(tempdir)
