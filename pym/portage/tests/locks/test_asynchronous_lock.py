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
			for force_thread in (True, False):
				for force_dummy in (True, False):
					async_lock = AsynchronousLock(path=path,
						scheduler=scheduler, _force_dummy=force_dummy,
						_force_thread=force_thread)
					async_lock.start()
					async_lock.wait()
					async_lock.unlock()
					self.assertEqual(async_lock.returncode, os.EX_OK)
		finally:
			shutil.rmtree(tempdir)
