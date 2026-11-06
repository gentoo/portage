# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.package.ebuild.config import config
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)


class MaskedUseTestCase(TestCase):
    def testMaskedUseMetadata(self):
        """
        MASKED_USE is ebuild metadata for EAPIs that support it. Like IUSE
        and REQUIRED_USE, values set by eclasses accumulate.
        """
        ebuilds = {
            "dev-vcs/git-1": {
                "EAPI": "9-masked-use",
                "IUSE": "perforce python_single_target_python3_13",
                "MASKED_USE": "!perforce? ( python_single_target_python3_13 )",
                "MISC_CONTENT": "inherit foo",
            },
            "dev-vcs/git-2": {
                "EAPI": "9",
                "IUSE": "perforce python_single_target_python3_13",
                "MASKED_USE": "!perforce? ( python_single_target_python3_13 )",
            },
        }
        eclasses = {
            "foo": (
                'IUSE="foo bar"',
                'MASKED_USE="!foo? ( bar )"',
            ),
        }

        playground = ResolverPlayground(ebuilds=ebuilds, eclasses=eclasses)
        try:
            portdb = playground.trees[playground.eroot]["porttree"].dbapi
            self.assertEqual(
                portdb.aux_get("dev-vcs/git-1", ["MASKED_USE"]),
                ["!perforce? ( python_single_target_python3_13 ) !foo? ( bar )"],
            )
            # Not supported by this EAPI, so it is not metadata.
            self.assertEqual(portdb.aux_get("dev-vcs/git-2", ["MASKED_USE"]), [""])
        finally:
            playground.cleanup()

    def testMaskedUseInvalid(self):
        """
        An ebuild with invalid MASKED_USE is masked.
        """
        ebuilds = {
            "dev-libs/valid-1": {
                "EAPI": "9-masked-use",
                "IUSE": "a b",
                "MASKED_USE": "!a? ( b )",
            },
            # The operators of REQUIRED_USE are not allowed.
            "dev-libs/invalid-1": {
                "EAPI": "9-masked-use",
                "IUSE": "a b",
                "MASKED_USE": "|| ( a b )",
            },
            # Flags must be in IUSE, both the masked ones
            "dev-libs/invalid-2": {
                "EAPI": "9-masked-use",
                "IUSE": "a",
                "MASKED_USE": "!a? ( b )",
            },
            # and the ones in conditionals.
            "dev-libs/invalid-3": {
                "EAPI": "9-masked-use",
                "IUSE": "b",
                "MASKED_USE": "!a? ( b )",
            },
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/valid"],
                success=True,
                mergelist=["dev-libs/valid-1"],
            ),
            ResolverPlaygroundTestCase(["=dev-libs/invalid-1"], success=False),
            ResolverPlaygroundTestCase(["=dev-libs/invalid-2"], success=False),
            ResolverPlaygroundTestCase(["=dev-libs/invalid-3"], success=False),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testMaskedUseSetcpv(self):
        """
        config.setcpv() disables the flags that MASKED_USE masks for the
        package's USE settings, and reports them in config.usemask.
        """
        py12 = "python_single_target_python3_12"
        py13 = "python_single_target_python3_13"
        iuse = frozenset(["perforce", py12, py13])
        metadata = {
            "EAPI": "9-masked-use",
            "IUSE": " ".join(sorted(iuse)),
            "MASKED_USE": f"!perforce? ( {py12} {py13} )",
        }
        ebuilds = {
            "dev-vcs/git-1": metadata,
            "dev-vcs/git-2": metadata,
            # MASKED_USE is ignored for an EAPI that does not support it.
            "dev-vcs/git-3": {**metadata, "EAPI": "9"},
        }
        user_config = {
            "make.conf": (f'USE="{py13}"',),
            "package.use": ("=dev-vcs/git-2 perforce",),
        }

        playground = ResolverPlayground(ebuilds=ebuilds, user_config=user_config)
        try:
            portdb = playground.trees[playground.eroot]["porttree"].dbapi
            settings = config(clone=playground.settings)

            def setcpv(cpv):
                settings.setcpv(cpv, mydb=portdb)
                return (
                    iuse.intersection(settings["PORTAGE_USE"].split()),
                    iuse.intersection(settings.usemask),
                )

            # Go back and forth, since setcpv() reuses the results of the
            # previous call when it can.
            for _ in range(2):
                self.assertEqual(setcpv("dev-vcs/git-1"), (set(), {py12, py13}))
                self.assertEqual(setcpv("dev-vcs/git-2"), ({"perforce", py13}, set()))
                self.assertEqual(setcpv("dev-vcs/git-3"), ({py13}, set()))
        finally:
            playground.cleanup()

    def testMaskedUseResolver(self):
        py12 = "python_single_target_python3_12"
        py13 = "python_single_target_python3_13"
        metadata = {
            "EAPI": "9-masked-use",
            "IUSE": f"perforce {py12} {py13}",
            "MASKED_USE": f"!perforce? ( {py12} {py13} )",
        }
        ebuilds = {
            "dev-vcs/git-1": metadata,
            # The same package, in an EAPI without MASKED_USE.
            "dev-vcs/nomask-1": {"EAPI": "9", "IUSE": metadata["IUSE"]},
            "app-misc/needs-git-py-1": {
                "EAPI": "9",
                "RDEPEND": f"dev-vcs/git[{py13}]",
            },
            "app-misc/needs-nomask-py-1": {
                "EAPI": "9",
                "RDEPEND": f"dev-vcs/nomask[{py13}]",
            },
        }
        # Built back when python3_12 was the selected target. With perforce
        # disabled, MASKED_USE had the package manager build git without
        # any target at all.
        installed = {
            "dev-vcs/git-1": {**metadata, "USE": ""},
            "dev-vcs/nomask-1": {"EAPI": "9", "IUSE": metadata["IUSE"], "USE": py12},
        }
        binpkgs = {
            "dev-vcs/git-1": {**metadata, "USE": ""},
        }
        user_config = {"make.conf": (f'USE="{py13}"',)}

        test_cases = (
            # A change of the python target does not rebuild a package for
            # which it is masked.
            ResolverPlaygroundTestCase(
                ["dev-vcs/git"],
                options={"--newuse": True},
                success=True,
                mergelist=[],
            ),
            ResolverPlaygroundTestCase(
                ["dev-vcs/nomask"],
                options={"--newuse": True},
                success=True,
                mergelist=["dev-vcs/nomask-1"],
            ),
            # A binary package matches whatever target is selected, including
            # when MASKED_USE has to come from the binary package itself.
            ResolverPlaygroundTestCase(
                ["dev-vcs/git"],
                options={"--usepkg": True, "--binpkg-respect-use": "y"},
                success=True,
                mergelist=["[binary]dev-vcs/git-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-vcs/git"],
                options={"--usepkgonly": True, "--binpkg-respect-use": "y"},
                success=True,
                mergelist=["[binary]dev-vcs/git-1"],
            ),
            # A masked flag is disabled, as far as USE dependencies go.
            ResolverPlaygroundTestCase(
                ["app-misc/needs-git-py"],
                options={"--autounmask": "n"},
                success=False,
            ),
            # Like a flag that is masked by the profile, autounmask does not
            # offer to enable it.
            ResolverPlaygroundTestCase(
                ["app-misc/needs-git-py"],
                success=False,
            ),
            ResolverPlaygroundTestCase(
                ["app-misc/needs-nomask-py"],
                options={"--autounmask": "n"},
                success=True,
                mergelist=["dev-vcs/nomask-1", "app-misc/needs-nomask-py-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds,
            installed=installed,
            binpkgs=binpkgs,
            user_config=user_config,
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testMaskedUseUnmasked(self):
        """
        Flags are not masked while the conditional is not satisfied.
        """
        py12 = "python_single_target_python3_12"
        py13 = "python_single_target_python3_13"
        metadata = {
            "EAPI": "9-masked-use",
            "IUSE": f"perforce {py12} {py13}",
            "MASKED_USE": f"!perforce? ( {py12} {py13} )",
        }
        ebuilds = {
            "dev-vcs/git-1": metadata,
            "app-misc/needs-git-py-1": {
                "EAPI": "9",
                "RDEPEND": f"dev-vcs/git[{py13}]",
            },
        }
        installed = {
            "dev-vcs/git-1": {**metadata, "USE": f"perforce {py12}"},
        }
        user_config = {
            "make.conf": (f'USE="{py13}"',),
            "package.use": ("dev-vcs/git perforce",),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-vcs/git"],
                options={"--newuse": True},
                success=True,
                mergelist=["dev-vcs/git-1"],
            ),
            ResolverPlaygroundTestCase(
                ["app-misc/needs-git-py"],
                options={"--autounmask": "n"},
                success=True,
                mergelist=["dev-vcs/git-1", "app-misc/needs-git-py-1"],
            ),
        )

        playground = ResolverPlayground(
            ebuilds=ebuilds, installed=installed, user_config=user_config
        )
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()
