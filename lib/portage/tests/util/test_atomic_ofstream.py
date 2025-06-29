# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import os
import stat
import tempfile

from portage.tests import TestCase
from portage.util import atomic_ofstream


class AtomicOFStreamTestCase(TestCase):
    def test_enospc_rollback(self):
        file_name = "foo"
        start_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as tempdir:
            try:
                os.chdir(tempdir)
                with self.assertRaises(OSError):
                    with atomic_ofstream(file_name) as f:
                        f.write("hello")
                        raise OSError(errno.ENOSPC, "No space left on device")
                self.assertFalse(os.path.exists(file_name))
                self.assertEqual(os.listdir(tempdir), [])
            finally:
                os.chdir(start_dir)

    def test_open_failure(self):
        file_name = "bad/path"
        start_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as tempdir:
            try:
                os.chdir(tempdir)
                with self.assertRaises(OSError):
                    with atomic_ofstream(file_name):
                        pass
                self.assertEqual(os.listdir(tempdir), [])
            finally:
                os.chdir(start_dir)

    def test_broken_symlink(self):
        content = "foo"
        broken_symlink = "symlink"
        symlink_targets = (("foo/bar/baz", False), ("baz", True))
        start_dir = os.getcwd()
        for symlink_target, can_follow in symlink_targets:
            with tempfile.TemporaryDirectory() as tempdir:
                try:
                    os.chdir(tempdir)
                    with open(broken_symlink, "w") as f:
                        default_file_mode = stat.S_IMODE(os.fstat(f.fileno()).st_mode)
                        os.unlink(broken_symlink)
                    os.symlink(symlink_target, broken_symlink)
                    with atomic_ofstream(broken_symlink) as f:
                        f.write(content)
                    with open(broken_symlink) as f:
                        self.assertEqual(f.read(), content)
                    self.assertEqual(os.path.islink(broken_symlink), can_follow)
                    self.assertEqual(
                        stat.S_IMODE(os.stat(broken_symlink).st_mode), default_file_mode
                    )
                finally:
                    os.chdir(start_dir)

    def test_preserves_mode(self):
        file_name = "foo"
        file_mode = 0o604
        start_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as tempdir:
            try:
                os.chdir(tempdir)
                with open(file_name, "wb"):
                    pass
                self.assertNotEqual(stat.S_IMODE(os.stat(file_name).st_mode), file_mode)
                os.chmod(file_name, file_mode)
                st_before = os.stat(file_name)
                self.assertEqual(stat.S_IMODE(st_before.st_mode), file_mode)
                with atomic_ofstream(file_name):
                    pass
                st_after = os.stat(file_name)
                self.assertNotEqual(st_before.st_ino, st_after.st_ino)
                self.assertEqual(stat.S_IMODE(st_after.st_mode), file_mode)
            finally:
                os.chdir(start_dir)
