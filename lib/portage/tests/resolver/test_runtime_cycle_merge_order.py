# Copyright 2016-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class RuntimeCycleMergeOrderTestCase(TestCase):
    def testRuntimeCycleMergeOrder(self):
        ebuilds = {
            "app-misc/plugins-consumer-1": {
                "EAPI": "6",
                "DEPEND": "app-misc/plugin-b:=",
                "RDEPEND": "app-misc/plugin-b:=",
            },
            "app-misc/plugin-b-1": {
                "EAPI": "6",
                "RDEPEND": "app-misc/runtime-cycle-b",
                "PDEPEND": "app-misc/plugins-consumer",
            },
            "app-misc/runtime-cycle-b-1": {
                "RDEPEND": "app-misc/plugin-b app-misc/branch-b",
            },
            "app-misc/branch-b-1": {
                "RDEPEND": "app-misc/leaf-b app-misc/branch-c",
            },
            "app-misc/leaf-b-1": {},
            "app-misc/branch-c-1": {
                "RDEPEND": "app-misc/runtime-cycle-c app-misc/runtime-c",
            },
            "app-misc/runtime-cycle-c-1": {
                "RDEPEND": "app-misc/branch-c",
            },
            "app-misc/runtime-c-1": {
                "RDEPEND": "app-misc/branch-d",
            },
            "app-misc/branch-d-1": {
                "RDEPEND": "app-misc/leaf-d app-misc/branch-e",
            },
            "app-misc/branch-e-1": {
                "RDEPEND": "app-misc/leaf-e",
            },
            "app-misc/leaf-d-1": {},
            "app-misc/leaf-e-1": {},
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["app-misc/plugin-b"],
                success=True,
                ambiguous_merge_order=True,
                mergelist=[
                    ("app-misc/leaf-b-1", "app-misc/leaf-d-1", "app-misc/leaf-e-1"),
                    ("app-misc/branch-d-1", "app-misc/branch-e-1"),
                    "app-misc/runtime-c-1",
                    ("app-misc/runtime-cycle-c-1", "app-misc/branch-c-1"),
                    "app-misc/branch-b-1",
                    ("app-misc/runtime-cycle-b-1", "app-misc/plugin-b-1"),
                    "app-misc/plugins-consumer-1",
                ],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testBuildtimeRuntimeCycleMergeOrder(self):
        installed = {
            "dev-util/cmake-3.26.5-r2": {
                "EAPI": "8",
                "KEYWORDS": "x86",
                "DEPEND": "net-misc/curl",
                "RDEPEND": "net-misc/curl",
            },
            "net-dns/c-ares-1.21.0": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "RDEPEND": "net-dns/c-ares",
            },
            "net-misc/curl-8.4.0": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "DEPEND": """
                    net-dns/c-ares
                    http2? ( net-libs/nghttp2:= )
                """,
                "RDEPEND": """
                    net-dns/c-ares
                    http2? ( net-libs/nghttp2:= )
                 """,
            },
            "net-dns/c-ares-1.21.0": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
            },
        }

        binpkgs = {
            "net-misc/curl-8.4.0": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "IUSE": "http2",
                "USE": "http2",
                "DEPEND": """
                    net-dns/c-ares
                    http2? ( net-libs/nghttp2:= )
                """,
                "RDEPEND": """
                    net-dns/c-ares
                    http2? ( net-libs/nghttp2:= )
                """,
            },
            "dev-util/cmake-3.26.5-r2": {
                "EAPI": "8",
                "KEYWORDS": "x86",
                "DEPEND": "net-misc/curl",
                "RDEPEND": "net-misc/curl",
            },
        }

        ebuilds = {
            "dev-util/cmake-3.26.5-r2": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "DEPEND": "net-misc/curl",
                "RDEPEND": "net-misc/curl",
            },
            "dev-util/cmake-3.27.8": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "~x86",
                "DEPEND": "net-misc/curl",
                "RDEPEND": "net-misc/curl",
            },
            "net-dns/c-ares-1.21.0": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
            },
            "net-libs/nghttp2-1.57.0": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "BDEPEND": "dev-util/cmake",
                "RDEPEND": "net-dns/c-ares",
            },
            "net-misc/curl-8.4.0": {
                "EAPI": "8",
                "SLOT": "0",
                "KEYWORDS": "x86",
                "IUSE": "http2",
                "DEPEND": """
                    net-dns/c-ares
                    http2? ( net-libs/nghttp2:= )
                """,
                "RDEPEND": """
                    net-dns/c-ares
                    http2? ( net-libs/nghttp2:= )
                """,
            },
        }

        world = ("dev-util/cmake",)

        test_cases = (
            ResolverPlaygroundTestCase(
                ["@world"],
                options={
                    "--verbose": True,
                    "--update": True,
                    "--deep": True,
                    "--newuse": True,
                    "--usepkg": True,
                },
                success=True,
                # It would also work to punt the dev-util/cmake upgrade
                # until the end, given it's already installed.
                mergelist=[
                    "dev-util/cmake-3.27.8",
                    "net-libs/nghttp2-1.57.0",
                    "[binary]net-misc/curl-8.4.0",
                ],
            ),
        )

        playground = ResolverPlayground(
            world=world,
            installed=installed,
            binpkgs=binpkgs,
            ebuilds=ebuilds,
            debug=False,
            user_config={
                "make.conf": (
                    'ACCEPT_KEYWORDS="~x86"',
                    'USE="http2"',
                ),
            },
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
