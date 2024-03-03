# Copyright 2017, 2023 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import shutil
import tempfile
from unittest.mock import patch

import pytest

from portage import os
from portage.tests import TestCase
from portage.checksum import perform_md5
from portage.util.file_copy import copyfile, _fastcopy


class CopyFileTestCase(TestCase):
    def testCopyFile(self):
        tempdir = tempfile.mkdtemp()
        try:
            src_path = os.path.join(tempdir, "src")
            dest_path = os.path.join(tempdir, "dest")
            content = b"foo"

            with open(src_path, "wb") as f:
                f.write(content)

            copyfile(src_path, dest_path)

            self.assertEqual(perform_md5(src_path), perform_md5(dest_path))
        finally:
            shutil.rmtree(tempdir)


class CopyFileSparseTestCase(TestCase):
    def testCopyFileSparse(self):
        tempdir = tempfile.mkdtemp()
        try:
            src_path = os.path.join(tempdir, "src")
            dest_path = os.path.join(tempdir, "dest")
            content = b"foo"

            # Use seek to create some sparse blocks. Don't make these
            # files too big, in case the filesystem doesn't support
            # sparse files.
            with open(src_path, "wb") as f:
                f.seek(2**16, os.SEEK_SET)
                f.write(content)
                f.seek(2**17, os.SEEK_SET)
                f.write(content)
                # Test that sparse blocks are handled correctly at
                # the end of the file.
                f.truncate(2**18)

            fastcopy_success = False

            def mock_fastcopy(src, dst):
                nonlocal fastcopy_success
                _fastcopy(src, dst)
                fastcopy_success = True

            with patch("portage.util.file_copy._fastcopy", new=mock_fastcopy):
                copyfile(src_path, dest_path)

            self.assertEqual(perform_md5(src_path), perform_md5(dest_path))

            src_stat = os.stat(src_path)
            dest_stat = os.stat(dest_path)

            self.assertEqual(src_stat.st_size, dest_stat.st_size)

            # If sparse blocks were preserved, then both files should
            # consume the same number of blocks.
            # This is expected to fail when sparse copy is not implemented.
            if src_stat.st_blocks != dest_stat.st_blocks:
                if fastcopy_success:
                    pytest.fail(reason="sparse copy failed with _fastcopy")
                pytest.xfail(reason="sparse copy is not implemented")
        finally:
            shutil.rmtree(tempdir)
