# Copyright 2011-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import tempfile
import traceback

import portage
from portage import os
from portage import shutil
from portage.exception import TryAgain
from portage.tests import TestCase

class LockNonblockTestCase(TestCase):

	def _testLockNonblock(self):
		tempdir = tempfile.mkdtemp()
		try:
			path = os.path.join(tempdir, 'lock_me')
			lock1 = portage.locks.lockfile(path)
			pid = os.fork()
			if pid == 0:
				portage._ForkWatcher.hook(portage._ForkWatcher)
				portage.locks._close_fds()
				 # Disable close_fds since we don't exec
				 # (see _setup_pipes docstring).
				portage.process._setup_pipes({0:0, 1:1, 2:2}, close_fds=False)
				rval = 2
				try:
					try:
						lock2 = portage.locks.lockfile(path, flags=os.O_NONBLOCK)
					except portage.exception.TryAgain:
						rval = os.EX_OK
					else:
						rval = 1
						portage.locks.unlockfile(lock2)
				except SystemExit:
					raise
				except:
					traceback.print_exc()
				finally:
					os._exit(rval)

			self.assertEqual(pid > 0, True)
			pid, status = os.waitpid(pid, 0)
			self.assertEqual(os.WIFEXITED(status), True)
			self.assertEqual(os.WEXITSTATUS(status), os.EX_OK)

			portage.locks.unlockfile(lock1)
		finally:
			shutil.rmtree(tempdir)

	def testLockNonblock(self):
		self._testLockNonblock()

	def testLockNonblockHardlink(self):
		prev_state = os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
		os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = "1"
		try:
			self._testLockNonblock()
		finally:
			os.environ.pop("__PORTAGE_TEST_HARDLINK_LOCKS", None)
			if prev_state is not None:
				os.environ["__PORTAGE_TEST_HARDLINK_LOCKS"] = prev_state

	def test_competition_with_same_process(self):
		"""
		Test that at attempt to lock the same file multiple times in the
		same process will behave as intended (bug 714480).
		"""
		tempdir = tempfile.mkdtemp()
		try:
			path = os.path.join(tempdir, 'lock_me')
			lock = portage.locks.lockfile(path)
			self.assertRaises(TryAgain, portage.locks.lockfile, path, flags=os.O_NONBLOCK)
			portage.locks.unlockfile(lock)
		finally:
			shutil.rmtree(tempdir)
