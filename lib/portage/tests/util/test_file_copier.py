# Copyright 2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import os
import shutil
import tempfile

from portage.tests import TestCase
from portage.util._async.FileCopier import FileCopier
from portage.util._eventloop.global_event_loop import global_event_loop


class FileCopierTestCase(TestCase):

	def testFileCopier(self):
		loop = global_event_loop()
		tempdir = tempfile.mkdtemp()
		try:

			# regular successful copy
			src_path = os.path.join(tempdir, 'src')
			dest_path = os.path.join(tempdir, 'dest')
			content = b'foo'
			with open(src_path, 'wb') as f:
				f.write(content)
			copier = FileCopier(src_path=src_path, dest_path=dest_path, scheduler=loop)
			copier.start()
			loop.run_until_complete(copier.async_wait())
			self.assertEqual(copier.returncode, 0)
			copier.future.result()
			with open(dest_path, 'rb') as f:
				self.assertEqual(f.read(), content)

			# failure due to nonexistent src_path
			src_path = os.path.join(tempdir, 'does-not-exist')
			copier = FileCopier(src_path=src_path, dest_path=dest_path, scheduler=loop)
			copier.start()
			loop.run_until_complete(copier.async_wait())
			self.assertEqual(copier.returncode, 1)
			self.assertEqual(copier.future.exception().errno, errno.ENOENT)
			self.assertEqual(copier.future.exception().filename, src_path.encode('utf8'))
		finally:
			shutil.rmtree(tempdir)
