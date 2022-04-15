# Copyright 2018-2022 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import tempfile
from portage import os
from portage import shutil
from portage.tests import TestCase
from portage.util.install_mask import InstallMask, install_mask_dir


class InstallMaskTestCase(TestCase):
    def testTrailingSlash(self):
        """
        Test that elements with a trailing slash match a directory
        but not a regular file.
        """
        cases = (
            (
                "/foo/bar/ -/foo/bar/*.foo -*.baz",
                (
                    (
                        "foo/bar/baz",
                        True,
                    ),
                    (
                        "foo/bar/",
                        True,
                    ),
                    # /foo/bar/ does not match
                    (
                        "foo/bar",
                        False,
                    ),
                    # this is excluded
                    (
                        "foo/bar/baz.foo",
                        False,
                    ),
                    # this is excluded
                    (
                        "foo/bar/baz.baz",
                        False,
                    ),
                    (
                        "foo/bar/baz.bar",
                        True,
                    ),
                ),
            ),
            (
                "/foo/bar -/foo/bar/*.foo -*.baz",
                (
                    (
                        "foo/bar/baz",
                        True,
                    ),
                    # /foo/bar matches both foo/bar/ and foo/bar
                    (
                        "foo/bar/",
                        True,
                    ),
                    (
                        "foo/bar",
                        True,
                    ),
                    # this is excluded
                    (
                        "foo/bar/baz.foo",
                        False,
                    ),
                    # this is excluded
                    (
                        "foo/bar/baz.baz",
                        False,
                    ),
                    (
                        "foo/bar/baz.bar",
                        True,
                    ),
                ),
            ),
            (
                "/foo*",
                (
                    (
                        "foo",
                        True,
                    ),
                    (
                        "foo/",
                        True,
                    ),
                    (
                        "foobar",
                        True,
                    ),
                    (
                        "foobar/",
                        True,
                    ),
                ),
            ),
            (
                "/foo*/",
                (
                    (
                        "foo",
                        False,
                    ),
                    (
                        "foo/",
                        True,
                    ),
                    (
                        "foobar",
                        False,
                    ),
                    (
                        "foobar/",
                        True,
                    ),
                ),
            ),
            (
                "/usr/share/locale "
                "-/usr/share/locale/en* "
                "-/usr/share/locale/kf5_all_languages "
                "-/usr/share/locale/locale.alias",
                (
                    (
                        "usr/share/locale/en",
                        False,
                    ),
                    (
                        "usr/share/locale/en_GB",
                        False,
                    ),
                    (
                        "usr/share/locale/en/kf5_all_languages",
                        False,
                    ),
                    (
                        "usr/share/locale/locale.alias",
                        False,
                    ),
                    (
                        "usr/share/locale/es",
                        True,
                    ),
                    (
                        "usr/share/locale/fr",
                        True,
                    ),
                    (
                        "usr/share/locale",
                        True,
                    ),
                ),
            ),
        )

        for install_mask_str, paths in cases:
            install_mask = InstallMask(install_mask_str)
            for path, expected in paths:
                self.assertEqual(
                    install_mask.match(path),
                    expected,
                    'unexpected match result for "{}" with path {}'.format(
                        install_mask_str, path
                    ),
                )

    def testSymlinkDir(self):
        """
        Test that masked symlinks to directories are removed.
        """
        tmp_dir = tempfile.mkdtemp()

        try:
            base_dir = os.path.join(tmp_dir, "foo")
            target_dir = os.path.join(tmp_dir, "foo", "bar")
            link_name = os.path.join(tmp_dir, "foo", "baz")

            os.mkdir(base_dir)
            os.mkdir(target_dir)
            os.symlink(target_dir, link_name)

            install_mask = InstallMask("/foo/")
            install_mask_dir(tmp_dir, install_mask)
            self.assertFalse(
                os.path.lexists(link_name), "failed to remove {}".format(link_name)
            )
            self.assertFalse(
                os.path.lexists(base_dir), "failed to remove {}".format(base_dir)
            )
        finally:
            shutil.rmtree(tmp_dir)
