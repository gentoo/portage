# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import shutil
import tempfile

from portage import os
from portage.tests import TestCase
from portage.checksum import perform_md5
from portage.util.file_copy import copyfile


class CopyFileTestCase(TestCase):

	def testCopyFile(self):

		tempdir = tempfile.mkdtemp()
		try:
			src_path = os.path.join(tempdir, 'src')
			dest_path = os.path.join(tempdir, 'dest')
			content = b'foo'

			with open(src_path, 'wb') as f:
				f.write(content)

			copyfile(src_path, dest_path)

			self.assertEqual(perform_md5(src_path), perform_md5(dest_path))
		finally:
			shutil.rmtree(tempdir)


class CopyFileSparseTestCase(TestCase):

	def testCopyFileSparse(self):

		tempdir = tempfile.mkdtemp()
		try:
			src_path = os.path.join(tempdir, 'src')
			dest_path = os.path.join(tempdir, 'dest')
			content = b'foo'

			# Use seek to create some sparse blocks. Don't make these
			# files too big, in case the filesystem doesn't support
			# sparse files.
			with open(src_path, 'wb') as f:
				f.write(content)
				f.seek(2**17, 1)
				f.write(content)
				f.seek(2**18, 1)
				f.write(content)
				# Test that sparse blocks are handled correctly at
				# the end of the file (involves seek and truncate).
				f.seek(2**17, 1)

			copyfile(src_path, dest_path)

			self.assertEqual(perform_md5(src_path), perform_md5(dest_path))

			# This last part of the test is expected to fail when sparse
			# copy is not implemented, so set the todo flag in order
			# to tolerate failures.
			self.todo = True

			# If sparse blocks were preserved, then both files should
			# consume the same number of blocks.
			self.assertEqual(
				os.stat(src_path).st_blocks,
				os.stat(dest_path).st_blocks)
		finally:
			shutil.rmtree(tempdir)
