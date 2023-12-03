# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class AlternativesGzipTestCase(TestCase):
    def testAlternativesGzip(self):
        """
        Test bug 917259, where app-alternatives/gzip is upgraded before
        its pigz RDEPEND is installed. This is triggered when
        find_smallest_cycle selects a large cycle and the topological
        sort produces poor results when leaf_nodes returns
        app-alternatives/gzip as part of a large group of nodes.
        This problem was solved by changing the topological sort to
        increase ignore_priority in order to select a smaller number
        of leaf nodes at a time.
        """
        ebuilds = {
            "app-alternatives/gzip-1": {
                "EAPI": "8",
                "RDEPEND": "reference? ( >=app-arch/gzip-1.12-r3 ) pigz? ( >=app-arch/pigz-2.8[-symlink(-)] )",
                "IUSE": "reference pigz",
                "REQUIRED_USE": "^^ ( reference pigz )",
            },
            "app-alternatives/gzip-0": {
                "EAPI": "8",
                "RDEPEND": "reference? ( >=app-arch/gzip-1.12-r3 ) pigz? ( app-arch/pigz[-symlink(-)] )",
                "IUSE": "reference pigz",
                "REQUIRED_USE": "^^ ( reference pigz )",
            },
            "app-arch/gzip-1.13": {
                "EAPI": "8",
                "RDEPEND": "!app-arch/pigz[symlink(-)]",
                "PDEPEND": "app-alternatives/gzip",
            },
            "app-arch/zstd-1.5.5": {
                "EAPI": "8",
                "DEPEND": ">=sys-libs/zlib-1.2.3",
                "RDEPEND": ">=sys-libs/zlib-1.2.3",
            },
            "app-arch/pigz-2.8": {
                "EAPI": "8",
                "DEPEND": ">=sys-libs/zlib-1.2.3",
                "RDEPEND": ">=sys-libs/zlib-1.2.3",
                "PDEPEND": "app-alternatives/gzip",
            },
            "dev-lang/perl-5.36.1-r3": {
                "EAPI": "8",
                "BDEPEND": ">=sys-libs/zlib-1.2.12 virtual/libcrypt:=",
                "RDEPEND": ">=sys-libs/zlib-1.2.12 virtual/libcrypt:=",
                "DEPEND": ">=sys-libs/zlib-1.2.12 virtual/libcrypt:=",
            },
            "dev-libs/libgcrypt-1.10.2": {
                "EAPI": "8",
                "SLOT": "0",
                "BDEPEND": ">=sys-devel/automake-1.16.5",
                "DEPEND": "sys-libs/glibc",
                "RDEPEND": "sys-libs/glibc",
            },
            "dev-libs/libpcre2-10.42-r1": {
                "EAPI": "8",
                "SLOT": "0/3",
                "DEPEND": "sys-libs/zlib",
                "RDEPEND": "sys-libs/zlib",
            },
            "sys-apps/locale-gen-2.23-r1": {
                "EAPI": "8",
                "RDEPEND": "app-alternatives/gzip",
            },
            "sys-apps/systemd-253.6": {
                "EAPI": "8",
                "SLOT": "0/2",
                "BDEPEND": "dev-lang/perl",
                "DEPEND": ">=sys-apps/util-linux-2.30:= >=dev-libs/libgcrypt-1.4.5:0= virtual/libcrypt:= dev-libs/libpcre2",
                "RDEPEND": ">=sys-apps/util-linux-2.30:= >=dev-libs/libgcrypt-1.4.5:0= virtual/libcrypt:= dev-libs/libpcre2",
            },
            "sys-apps/util-linux-2.38.1-r2": {
                "EAPI": "8",
                "BDEPEND": ">=sys-devel/automake-1.16.5",
                "DEPEND": "virtual/libcrypt:= sys-libs/zlib:= virtual/libudev:= dev-libs/libpcre2:=",
                "RDEPEND": "sys-apps/systemd sys-libs/zlib:= virtual/libudev:= dev-libs/libpcre2:=",
            },
            "sys-devel/automake-1.16.5-r1": {
                "EAPI": "8",
                "BDEPEND": "app-alternatives/gzip",
                "RDEPEND": ">=dev-lang/perl-5.6",
            },
            "sys-libs/glibc-2.37-r7": {
                "EAPI": "8",
                "BDEPEND": "sys-apps/locale-gen",
                "IDEPEND": "sys-apps/locale-gen",
                "RDEPEND": "dev-lang/perl",
            },
            "sys-libs/libxcrypt-4.4.36": {
                "BDEPEND": "dev-lang/perl",
                "DEPEND": "sys-libs/glibc",
                "RDEPEND": "sys-libs/glibc",
            },
            "sys-libs/zlib-1.3-r1": {
                "EAPI": "8",
                "SLOT": "0/1",
                "BDEPEND": ">=sys-devel/automake-1.16.5",
            },
            "sys-libs/zlib-1.2.13-r2": {
                "EAPI": "8",
                "SLOT": "0/1",
                "BDEPEND": ">=sys-devel/automake-1.16.5",
            },
            "virtual/libcrypt-2-r1": {
                "EAPI": "8",
                "SLOT": "0/2",
                "RDEPEND": "sys-libs/libxcrypt",
            },
            "virtual/libudev-251-r2": {
                "EAPI": "8",
                "SLOT": "0/1",
                "RDEPEND": ">=sys-apps/systemd-251:0/2",
            },
        }

        installed = {
            "app-alternatives/gzip-0": {
                "EAPI": "8",
                "RDEPEND": "reference? ( >=app-arch/gzip-1.12-r3 ) pigz? ( app-arch/pigz[-symlink(-)] )",
                "IUSE": "reference pigz",
                "USE": "reference",
            },
            "app-arch/gzip-1.13": {
                "EAPI": "8",
                "RDEPEND": "!app-arch/pigz[symlink(-)]",
                "PDEPEND": "app-alternatives/gzip",
            },
            "app-arch/zstd-1.5.5": {
                "EAPI": "8",
                "DEPEND": ">=sys-libs/zlib-1.2.3",
                "RDEPEND": ">=sys-libs/zlib-1.2.3",
            },
            "dev-lang/perl-5.36.1-r3": {
                "EAPI": "8",
                "BDEPEND": ">=sys-libs/zlib-1.2.12 virtual/libcrypt:0/2=",
                "RDEPEND": ">=sys-libs/zlib-1.2.12 virtual/libcrypt:0/2=",
                "DEPEND": ">=sys-libs/zlib-1.2.12 virtual/libcrypt:0/2=",
            },
            "dev-libs/libgcrypt-1.10.2": {
                "EAPI": "8",
                "SLOT": "0",
                "BDEPEND": ">=sys-devel/automake-1.16.5",
                "DEPEND": "sys-libs/glibc",
                "RDEPEND": "sys-libs/glibc",
            },
            "dev-libs/libpcre2-10.42-r1": {
                "EAPI": "8",
                "SLOT": "0/3",
                "DEPEND": "sys-libs/zlib",
                "RDEPEND": "sys-libs/zlib",
            },
            "sys-apps/locale-gen-2.23-r1": {
                "EAPI": "8",
                "RDEPEND": "app-alternatives/gzip",
            },
            "sys-apps/systemd-253.6": {
                "EAPI": "8",
                "SLOT": "0/2",
                "BDEPEND": "dev-lang/perl",
                "DEPEND": ">=sys-apps/util-linux-2.30:0= >=dev-libs/libgcrypt-1.4.5:0= virtual/libcrypt:0/2= dev-libs/libpcre2",
                "RDEPEND": ">=sys-apps/util-linux-2.30:0= >=dev-libs/libgcrypt-1.4.5:0= virtual/libcrypt:0/2= dev-libs/libpcre2",
            },
            "sys-apps/util-linux-2.38.1-r2": {
                "EAPI": "8",
                "BDEPEND": ">=sys-devel/automake-1.16.5",
                "DEPEND": "virtual/libcrypt:0/2= sys-libs/zlib:0/1= virtual/libudev:0/1= dev-libs/libpcre2:0/3=",
                "RDEPEND": "sys-apps/systemd sys-libs/zlib:0/1= virtual/libudev:0/1= dev-libs/libpcre2:0/3=",
            },
            "sys-devel/automake-1.16.5-r1": {
                "EAPI": "8",
                "BDEPEND": "app-alternatives/gzip",
                "RDEPEND": ">=dev-lang/perl-5.6",
            },
            "sys-libs/glibc-2.37-r7": {
                "EAPI": "8",
                "BDEPEND": "sys-apps/locale-gen",
                "IDEPEND": "sys-apps/locale-gen",
                "RDEPEND": "dev-lang/perl",
            },
            "sys-libs/libxcrypt-4.4.36": {
                "BDEPEND": "dev-lang/perl",
                "DEPEND": "sys-libs/glibc",
                "RDEPEND": "sys-libs/glibc",
            },
            "sys-libs/zlib-1.2.13-r2": {
                "EAPI": "8",
                "SLOT": "0/1",
                "BDEPEND": ">=sys-devel/automake-1.16.5",
            },
            "virtual/libcrypt-2-r1": {
                "EAPI": "8",
                "SLOT": "0/2",
                "RDEPEND": "sys-libs/libxcrypt",
            },
            "virtual/libudev-251-r2": {
                "EAPI": "8",
                "SLOT": "0/1",
                "RDEPEND": ">=sys-apps/systemd-251:0/2",
            },
        }

        world = [
            "app-alternatives/gzip",
            "app-arch/gzip",
            "app-arch/zstd",
            "sys-apps/systemd",
        ]

        user_config = {
            "package.use": ("app-alternatives/gzip -reference pigz",),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["app-alternatives/gzip", "sys-libs/zlib"],
                success=True,
                mergelist=[
                    "sys-libs/zlib-1.3-r1",
                    "app-arch/pigz-2.8",
                    "app-alternatives/gzip-1",
                ],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            world=world,
            user_config=user_config,
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
