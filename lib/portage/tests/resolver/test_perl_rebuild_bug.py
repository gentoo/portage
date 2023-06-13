# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class PerlRebuildBugTestCase(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def testPerlRebuildBug(self):
        """
        The infamous Perl rebuild bug.

        A non-slotted build-time dependency cycle is created by:
        dev-lang/perl -> sys-libs/zlib -> sys-devel/automake -> dev-lang/perl
        Everything else depends on this cycle.

        Bug in solving for smallest cycle causes slot in RDEPEND of
        dev-perl/Locale-gettext to be ignored, so all dependencies other than
        perl's >=sys-libs/zlib-1.2.12 are satisfied by already-installed
        packages. dev-perl/Locale-gettext and sys-devel/automake become leaves
        of the depgraph after satisfied packages are ignored. They become
        emerged first. This causes an issue because dev-perl/Locale-gettext is
        now built before the slot upgrade of dev-lang/perl.
        """
        ebuilds = {
            "dev-lang/perl-5.36.0-r2": {
                "EAPI": "5",
                "DEPEND": ">=sys-libs/zlib-1.2.12",
                "RDEPEND": ">=sys-libs/zlib-1.2.12",
                "SLOT": "0/5.36",
            },
            "dev-perl/Locale-gettext-1.70.0-r1": {
                "EAPI": "5",
                "DEPEND": "dev-lang/perl",
                "RDEPEND": "dev-lang/perl:=",
            },
            "sys-apps/help2man-1.49.3": {
                "EAPI": "5",
                "DEPEND": "dev-lang/perl dev-perl/Locale-gettext",
                "RDEPEND": "dev-lang/perl dev-perl/Locale-gettext",
            },
            "sys-devel/automake-1.16.5": {
                "EAPI": "5",
                "DEPEND": "dev-lang/perl",
                "RDEPEND": "dev-lang/perl",
            },
            "sys-libs/zlib-1.2.13-r1": {
                "EAPI": "5",
                "DEPEND": "sys-devel/automake",
            },
        }

        installed = {
            "dev-lang/perl-5.34.0-r3": {
                "EAPI": "5",
                "DEPEND": "sys-libs/zlib",
                "RDEPEND": "sys-libs/zlib",
                "SLOT": "0/5.34",
            },
            "dev-perl/Locale-gettext-1.70.0-r1": {
                "EAPI": "5",
                "DEPEND": "dev-lang/perl",
                "RDEPEND": "dev-lang/perl:0/5.34=",
            },
            "sys-apps/help2man-1.48.5": {
                "EAPI": "5",
                "DEPEND": "dev-lang/perl dev-perl/Locale-gettext",
                "RDEPEND": "dev-lang/perl dev-perl/Locale-gettext",
            },
            "sys-devel/automake-1.16.4": {
                "EAPI": "5",
                "DEPEND": "dev-lang/perl",
                "RDEPEND": "dev-lang/perl",
            },
            "sys-libs/zlib-1.2.11-r4": {
                "EAPI": "5",
                "DEPEND": "sys-devel/automake",
            },
        }

        world = ["sys-apps/help2man"]

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={"--deep": True, "--update": True, "--verbose": True},
                success=True,
                ambiguous_merge_order=True,
                merge_order_assertions=(
                    (
                        "dev-lang/perl-5.36.0-r2",
                        "dev-perl/Locale-gettext-1.70.0-r1",
                    ),
                ),
                mergelist=[
                    "sys-devel/automake-1.16.5",
                    "sys-libs/zlib-1.2.13-r1",
                    "dev-lang/perl-5.36.0-r2",
                    "dev-perl/Locale-gettext-1.70.0-r1",
                    "sys-apps/help2man-1.49.3",
                ],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            world=world,
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
