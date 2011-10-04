# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import shutil
import tempfile
import traceback

import portage
from portage import os
from portage.tests import TestCase

class LockNonblockTestCase(TestCase):

	def testLockNonblock(self):
		tempdir = tempfile.mkdtemp()
		try:
			path = os.path.join(tempdir, 'lock_me')
			lock1 = portage.locks.lockfile(path)
			pid = os.fork()
			if pid == 0:
				portage.process._setup_pipes({0:0, 1:1, 2:2})
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

