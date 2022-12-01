# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

from portage.const import SUPPORTED_GENTOO_BINPKG_FORMATS
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.output import colorize


class SlotOperatorUnsolvedTestCase(TestCase):
    """
    Demonstrate bug #456340, where an unsolved circular dependency
    interacts with an unsatisfied built slot-operator dep.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def testSlotOperatorUnsolved(self):
        ebuilds = {
            "dev-libs/icu-50.1.2": {"EAPI": "5", "SLOT": "0/50.1.2"},
            "net-libs/webkit-gtk-1.10.2-r300": {
                "EAPI": "5",
                "DEPEND": ">=dev-libs/icu-3.8.1-r1:=",
                "RDEPEND": ">=dev-libs/icu-3.8.1-r1:=",
            },
            "dev-ruby/rdoc-3.12.1": {
                "EAPI": "5",
                "IUSE": "test",
                "DEPEND": "test? ( >=dev-ruby/hoe-2.7.0 )",
            },
            "dev-ruby/hoe-2.13.0": {
                "EAPI": "5",
                "IUSE": "test",
                "DEPEND": "test? ( >=dev-ruby/rdoc-3.10 )",
                "RDEPEND": "test? ( >=dev-ruby/rdoc-3.10 )",
            },
        }

        binpkgs = {
            "net-libs/webkit-gtk-1.10.2-r300": {
                "EAPI": "5",
                "DEPEND": ">=dev-libs/icu-3.8.1-r1:0/50=",
                "RDEPEND": ">=dev-libs/icu-3.8.1-r1:0/50=",
            },
        }

        installed = {
            "dev-libs/icu-50.1.2": {"EAPI": "5", "SLOT": "0/50.1.2"},
            "net-libs/webkit-gtk-1.10.2-r300": {
                "EAPI": "5",
                "DEPEND": ">=dev-libs/icu-3.8.1-r1:0/50=",
                "RDEPEND": ">=dev-libs/icu-3.8.1-r1:0/50=",
            },
        }

        user_config = {"make.conf": ("FEATURES=test",)}

        world = ["net-libs/webkit-gtk", "dev-ruby/hoe"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--update": True, "--deep": True, "--usepkg": True},
                circular_dependency_solutions={
                    "dev-ruby/hoe-2.13.0": frozenset([frozenset([("test", False)])]),
                    "dev-ruby/rdoc-3.12.1": frozenset([frozenset([("test", False)])]),
                },
                success=False,
            ),
        )

        for binpkg_format in SUPPORTED_GENTOO_BINPKG_FORMATS:
            with self.subTest(binpkg_format=binpkg_format):
                print(colorize("HILITE", binpkg_format), end=" ... ")
                sys.stdout.flush()
                _user_config = user_config.copy()
                _user_config["make.conf"] += ('BINPKG_FORMAT="%s"' % binpkg_format,)
                playground = ResolverPlayground(
                    ebuilds=ebuilds,
                    binpkgs=binpkgs,
                    installed=installed,
                    user_config=_user_config,
                    world=world,
                    debug=False,
                )
                try:
                    for test_case in test_cases:
                        playground.run_TestCase(test_case)
                        self.assertEqual(
                            test_case.test_success, True, test_case.fail_msg
                        )
                finally:
                    playground.cleanup()
