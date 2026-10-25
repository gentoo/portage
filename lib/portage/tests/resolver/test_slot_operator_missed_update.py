# Copyright 2020-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import pytest

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class BacktrackMissedUpdateTestCase(TestCase):
    def testBacktrackMissedUpdateTestCase(self):
        ebuilds = {
            "dev-lang/python-2.7.18-r2": {
                "EAPI": "7",
                "SLOT": "2.7",
            },
            "dev-python/pypy3-7.3.2_rc2_p37-r1": {
                "EAPI": "7",
                "SLOT": "0/pypy37-pp73",
            },
            "dev-python/pypy3-7.3.1-r3": {
                "EAPI": "7",
                "SLOT": "0/pypy36-pp73",
            },
            "dev-python/setuptools-50.3.0": {
                "EAPI": "7",
                "IUSE": "python_targets_pypy3",
                "RDEPEND": "python_targets_pypy3? ( dev-python/pypy3:= )",
            },
            "dev-python/setuptools-50.2.0": {
                "EAPI": "7",
                "IUSE": "python_targets_pypy3",
                "RDEPEND": "python_targets_pypy3? ( dev-python/pypy3:= )",
            },
            "dev-python/setuptools-50.1.0": {
                "EAPI": "7",
                "IUSE": "python_targets_pypy3",
                "RDEPEND": "python_targets_pypy3? ( dev-python/pypy3:= )",
            },
            "dev-python/setuptools-49.6.0": {
                "EAPI": "7",
                "IUSE": "python_targets_pypy3",
                "RDEPEND": "python_targets_pypy3? ( dev-python/pypy3:= )",
            },
            "dev-python/setuptools-46.4.0-r2": {
                "EAPI": "7",
                "IUSE": "+python_targets_pypy3 +python_targets_python2_7",
                "RDEPEND": "python_targets_pypy3? ( dev-python/pypy3:= )",
            },
            "dev-lang/python-2.7.18-r2": {
                "EAPI": "7",
                "IUSE": "+python_targets_pypy3 +python_targets_python2_7",
                "RDEPEND": "python_targets_pypy3? ( dev-python/pypy3:= )",
            },
            "dev-vcs/mercurial-5.5.1": {
                "EAPI": "7",
                "IUSE": "+python_targets_pypy3 +python_targets_python2_7",
                "RDEPEND": "dev-python/setuptools[python_targets_pypy3?,python_targets_python2_7?] python_targets_python2_7? ( dev-lang/python:2.7 ) python_targets_pypy3? ( dev-python/pypy3:= )",
            },
        }

        installed = {
            "dev-lang/python-2.7.18-r2": {
                "EAPI": "7",
                "SLOT": "2.7",
            },
            "dev-python/pypy3-7.3.1-r3": {
                "EAPI": "7",
                "SLOT": "0/pypy36-pp73",
            },
            "dev-python/setuptools-46.4.0-r2": {
                "EAPI": "7",
                "IUSE": "+python_targets_pypy3 +python_targets_python2_7",
                "USE": "python_targets_pypy3 python_targets_python2_7",
                "RDEPEND": "dev-python/pypy3:0/pypy36-pp73=",
            },
            "dev-vcs/mercurial-5.5.1": {
                "EAPI": "7",
                "IUSE": "+python_targets_pypy3 +python_targets_python2_7",
                "USE": "python_targets_pypy3 python_targets_python2_7",
                "RDEPEND": "dev-python/setuptools[python_targets_pypy3,python_targets_python2_7] dev-python/pypy3:0/pypy36-pp73=",
            },
        }

        world = ["dev-vcs/mercurial"]

        test_cases = (
            # Bug 743115: missed updates trigger excessive backtracking
            ResolverPlaygroundTestCase(
                [">=dev-python/pypy3-7.3.2_rc", "@world"],
                options={"--update": True, "--deep": True, "--backtrack": 4},
                success=True,
                mergelist=[
                    "dev-python/pypy3-7.3.2_rc2_p37-r1",
                    "dev-python/setuptools-46.4.0-r2",
                    "dev-vcs/mercurial-5.5.1",
                ],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, world=world, debug=False
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.debug = False
            playground.cleanup()

    @pytest.mark.xfail(reason="bug #984929")
    def testBacktrackMissedOpenSSLUpdateTestCase(self):
        ebuilds = {
            "app-misc/foo-1.0.0": {
                "EAPI": "8",
                "RDEPEND": "dev-libs/openssl:=",
                "DEPEND": "dev-libs/openssl:=",
            },
            "dev-libs/openssl-3.6.5": {
                "EAPI": "8",
                "SLOT": "0/3",
            },
            "dev-libs/openssl-4.1.0": {
                "EAPI": "8",
                "SLOT": "0/4",
            },
            "dev-libs/openssl-compat-3.6.5": {
                "EAPI": "8",
                "SLOT": "3",
            },
            "x11-drivers/nvidia-drivers-615.78.08": {
                "EAPI": "8",
                "RDEPEND": "|| ( dev-libs/openssl-compat:3 dev-libs/openssl:0/3 )",
            },
        }

        installed = {
            "app-misc/foo-1.0.0": {
                "EAPI": "8",
                "RDEPEND": "dev-libs/openssl:0/3=",
                "DEPEND": "dev-libs/openssl:0/3=",
            },
            "dev-libs/openssl-3.6.5": {
                "EAPI": "8",
                "SLOT": "0/3",
            },
            "x11-drivers/nvidia-drivers-615.78.08": {
                "EAPI": "8",
                "RDEPEND": "|| ( dev-libs/openssl-compat:3 dev-libs/openssl:0/3 )",
            },
        }

        world = ["x11-drivers/nvidia-drivers"]

        test_cases = (
            # We want a subslot rebuild here as well
            ResolverPlaygroundTestCase(
                ["@world", "app-misc/foo"],
                options={"--update": True, "--deep": True},
                success=True,
                mergelist=[
                    # Swapping openssl{,-compat} would be OK too
                    "dev-libs/openssl-4.1.0",
                    "dev-libs/openssl-compat-3.6.5",
                    "app-misc/foo-1.0.0",
                ],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, world=world, debug=False
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.debug = False
            playground.cleanup()
