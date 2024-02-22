# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import shutil
import subprocess
import os

import portage
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class CrossDepPriorityTestCase(TestCase):
    def testCrossDepPriority(self):
        """
        Test bug 919174, where cross-root merge to an empty root
        failed due to circular dependencies.
        """
        ebuilds = {
            "dev-lang/python-3.11.6": {
                "EAPI": "8",
                "DEPEND": "sys-apps/util-linux:=",
                "RDEPEND": "sys-apps/util-linux:=",
            },
            "sys-apps/util-linux-2.38.1-r2": {
                "EAPI": "8",
                "DEPEND": "selinux? ( >=sys-libs/libselinux-2.2.2-r4 )",
                "RDEPEND": "selinux? ( >=sys-libs/libselinux-2.2.2-r4 )",
                "IUSE": "selinux",
            },
            "sys-libs/libselinux-3.5-r1": {
                "EAPI": "8",
                "DEPEND": "python? ( dev-lang/python )",
                "RDEPEND": "python? ( dev-lang/python )",
                "IUSE": "python",
            },
            "dev-libs/gmp-6.3.0": {
                "EAPI": "8",
                "SLOT": "0/10.4",
                "DEPEND": "cxx? ( sys-devel/gcc )",
                "RDEPEND": "cxx? ( sys-devel/gcc )",
                "IUSE": "cxx",
            },
            "sys-devel/gcc-13.2.1_p20230826": {
                "EAPI": "8",
                "DEPEND": ">=dev-libs/gmp-4.3.2:0=",
                "RDEPEND": ">=dev-libs/gmp-4.3.2:0=",
            },
        }

        installed = {
            "dev-lang/python-3.11.6": {
                "EAPI": "8",
                "KEYWORDS": "x86",
                "DEPEND": "sys-apps/util-linux:0/0=",
                "RDEPEND": "sys-apps/util-linux:0/0=",
            },
            "sys-apps/util-linux-2.38.1-r2": {
                "EAPI": "8",
                "KEYWORDS": "x86",
                "DEPEND": "selinux? ( >=sys-libs/libselinux-2.2.2-r4 )",
                "RDEPEND": "selinux? ( >=sys-libs/libselinux-2.2.2-r4 )",
                "IUSE": "selinux",
                "USE": "selinux",
            },
            "sys-libs/libselinux-3.5-r1": {
                "EAPI": "8",
                "KEYWORDS": "x86",
                "DEPEND": "python? ( dev-lang/python )",
                "RDEPEND": "python? ( dev-lang/python )",
                "IUSE": "python",
                "USE": "python",
            },
            "dev-libs/gmp-6.3.0": {
                "EAPI": "8",
                "KEYWORDS": "x86",
                "SLOT": "0/10.4",
                "DEPEND": "cxx? ( sys-devel/gcc )",
                "RDEPEND": "cxx? ( sys-devel/gcc )",
                "IUSE": "cxx",
                "USE": "cxx",
            },
            "sys-devel/gcc-13.2.1_p20230826": {
                "EAPI": "8",
                "KEYWORDS": "x86",
                "DEPEND": ">=dev-libs/gmp-4.3.2:0/10.4=",
                "RDEPEND": ">=dev-libs/gmp-4.3.2:0/10.4=",
            },
        }

        world = [
            "sys-apps/util-linux",
            "sys-devel/gcc",
        ]

        user_config = {
            "make.conf": ('USE="cxx python selinux"',),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--emptytree": True},
                success=True,
                mergelist=[
                    "dev-libs/gmp-6.3.0",
                    "sys-devel/gcc-13.2.1_p20230826",
                    "sys-apps/util-linux-2.38.1-r2",
                    "dev-lang/python-3.11.6",
                    "sys-libs/libselinux-3.5-r1",
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

            # Since ResolverPlayground does not internally support
            # cross-root, test with emerge.
            cross_root = os.path.join(playground.settings["EPREFIX"], "cross_root")
            world_file = os.path.join(
                cross_root,
                playground.settings["EPREFIX"].lstrip(os.sep),
                portage.const.WORLD_FILE,
            )
            os.makedirs(os.path.dirname(world_file))
            shutil.copy(
                os.path.join(playground.settings["EPREFIX"], portage.const.WORLD_FILE),
                world_file,
            )
            result = subprocess.run(
                [
                    "emerge",
                    f"--root={cross_root}",
                    "--pretend",
                    "--verbose",
                    "--usepkgonly",
                    "--quickpkg-direct=y",
                    "@world",
                ],
                env=playground.settings.environ(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            output = result.stdout.decode(errors="replace")
            try:
                self.assertTrue("5 packages (5 new, 5 binaries)" in output)
                self.assertEqual(result.returncode, os.EX_OK)
            except Exception:
                print(output)
                raise
        finally:
            playground.cleanup()
