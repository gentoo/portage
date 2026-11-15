# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import contextlib
import io

import portage
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
                "EAPI": "10-pre",
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
                "EAPI": "10-pre",
                "IUSE": "a b",
                "MASKED_USE": "!a? ( b )",
            },
            # The operators of REQUIRED_USE are not allowed.
            "dev-libs/invalid-1": {
                "EAPI": "10-pre",
                "IUSE": "a b",
                "MASKED_USE": "|| ( a b )",
            },
            # Flags must be in IUSE, both the masked ones
            "dev-libs/invalid-2": {
                "EAPI": "10-pre",
                "IUSE": "a",
                "MASKED_USE": "!a? ( b )",
            },
            # and the ones in conditionals.
            "dev-libs/invalid-3": {
                "EAPI": "10-pre",
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
            "EAPI": "10-pre",
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
            "EAPI": "10-pre",
            "IUSE": f"perforce {py12} {py13}",
            "MASKED_USE": f"!perforce? ( {py12} {py13} )",
        }
        ebuilds = {
            "dev-vcs/git-1": metadata,
            # REQUIRED_USE is checked after MASKED_USE has been applied.
            "dev-libs/required-1": {
                "EAPI": "10-pre",
                "IUSE": "a +b",
                "MASKED_USE": "!a? ( b )",
                "REQUIRED_USE": "!a? ( !b )",
            },
            # The same package, in an EAPI without MASKED_USE.
            "dev-vcs/nomask-1": {"EAPI": "9", "IUSE": metadata["IUSE"]},
            "app-misc/needs-git-py-1": {
                "EAPI": "9",
                "RDEPEND": f"dev-vcs/git[{py13}]",
            },
            "app-misc/needs-git-perforce-py-1": {
                "EAPI": "9",
                "RDEPEND": f"dev-vcs/git[perforce,{py13}]",
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
            # No ebuild, so MASKED_USE has to come from the binary package.
            "dev-vcs/binonly-1": {**metadata, "USE": ""},
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
            # A binary package matches whatever target is selected.
            ResolverPlaygroundTestCase(
                ["dev-vcs/git"],
                options={"--usepkg": True, "--binpkg-respect-use": "y"},
                success=True,
                mergelist=["[binary]dev-vcs/git-1"],
            ),
            ResolverPlaygroundTestCase(
                ["dev-vcs/binonly"],
                options={"--usepkgonly": True, "--binpkg-respect-use": "y"},
                success=True,
                mergelist=["[binary]dev-vcs/binonly-1"],
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
            # Nor does it take into account that enabling perforce would
            # unmask the target.
            ResolverPlaygroundTestCase(
                ["app-misc/needs-git-perforce-py"],
                success=False,
            ),
            ResolverPlaygroundTestCase(
                ["dev-libs/required"],
                success=True,
                mergelist=["dev-libs/required-1"],
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
            "EAPI": "10-pre",
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

    def testMaskedUseDisplay(self):
        """
        The merge list shows flags masked by MASKED_USE in a MASKED_USE
        variable of their own, grouped by the conditionals that mask them,
        instead of showing them like flags masked by the profile.
        """
        py = "python_single_target_python3_"
        ebuilds = {
            "dev-vcs/git-1": {
                "EAPI": "10-pre",
                "IUSE": f"gui perforce gtk qt6 tk {py}12 {py}13",
                "MASKED_USE": f"!perforce? ( {py}12 {py}13 ) !gui? ( gtk qt6 )",
            },
            # Only part of PYTHON_SINGLE_TARGET is masked.
            "dev-libs/partial-1": {
                "EAPI": "10-pre",
                "IUSE": f"a {py}12 {py}13",
                "MASKED_USE": f"!a? ( {py}12 )",
            },
            "dev-libs/nested-1": {
                "EAPI": "10-pre",
                "IUSE": "a b c",
                "MASKED_USE": "a? ( !b? ( c ) ) b? ( c )",
            },
            "dev-libs/unconditional-1": {
                "EAPI": "10-pre",
                "IUSE": "a x",
                "MASKED_USE": "x",
            },
            # Conditionals see USE before anything is masked, so the cause
            # of b is not mistaken for -b.
            "dev-libs/chained-1": {
                "EAPI": "10-pre",
                "IUSE": "a b c",
                "MASKED_USE": "a? ( b ) !b? ( c )",
            },
        }
        profile = {"use.mask": ("tk",)}
        user_config = {
            "make.conf": ('USE_EXPAND="PYTHON_SINGLE_TARGET"',),
            "package.use": (
                "dev-libs/nested a c",
                "dev-libs/chained a b c",
            ),
        }
        expected = {
            "dev-vcs/git-1": (
                'USE="-gui -perforce (-tk)" '
                'MASKED_USE="-perforce => PYTHON_SINGLE_TARGET, -gui => gtk qt6"'
            ),
            "dev-libs/partial-1": (
                'USE="-a" PYTHON_SINGLE_TARGET="-python3_13" '
                f'MASKED_USE="-a => {py}12"'
            ),
            "dev-libs/nested-1": 'USE="a -b" MASKED_USE="a,-b => c"',
            "dev-libs/unconditional-1": 'USE="-a" MASKED_USE="x"',
            "dev-libs/chained-1": 'USE="a c" MASKED_USE="a => b"',
        }

        playground = ResolverPlayground(
            ebuilds=ebuilds, profile=profile, user_config=user_config
        )
        try:
            for cpv, use_str in expected.items():
                result = playground.run(
                    [f"={cpv}"], options={"--pretend": True, "--verbose": True}
                )
                self.assertEqual(result.success, True, cpv)
                self.assertEqual(
                    self._merge_list_use(result.depgraph, cpv), use_str, cpv
                )
        finally:
            playground.cleanup()

    def testMaskedUseDisplayBinpkg(self):
        """
        A binary package shows the MASKED_USE flags for the USE settings it
        was built with, rather than those of the configuration.
        """
        py = "python_single_target_python3_"
        metadata = {
            "EAPI": "10-pre",
            "IUSE": f"perforce {py}12 {py}13",
            "MASKED_USE": f"!perforce? ( {py}12 {py}13 )",
        }
        binpkgs = {
            "dev-vcs/git-1": {**metadata, "USE": f"perforce {py}13"},
            "dev-vcs/git-2": {**metadata, "USE": ""},
        }
        expected = {
            # Without perforce in USE, the python targets are masked by the
            # configuration, but not by the USE that git-1 was built with.
            (): {
                "dev-vcs/git-1": 'USE="perforce" '
                'PYTHON_SINGLE_TARGET="(python3_13) (-python3_12)"',
                "dev-vcs/git-2": 'USE="-perforce" '
                'MASKED_USE="-perforce => PYTHON_SINGLE_TARGET"',
            },
            ("dev-vcs/git perforce",): {
                "dev-vcs/git-1": 'USE="perforce" '
                'PYTHON_SINGLE_TARGET="python3_13 -python3_12"',
                "dev-vcs/git-2": 'USE="-perforce" '
                'MASKED_USE="-perforce => PYTHON_SINGLE_TARGET"',
            },
        }

        for package_use, expected_use in expected.items():
            playground = ResolverPlayground(
                binpkgs=binpkgs,
                user_config={
                    "make.conf": (
                        'USE_EXPAND="PYTHON_SINGLE_TARGET"',
                        f'USE="{py}13"',
                    ),
                    "package.use": package_use,
                },
            )
            try:
                for cpv, use_str in expected_use.items():
                    result = playground.run(
                        [f"={cpv}"],
                        options={
                            "--pretend": True,
                            "--usepkgonly": True,
                            "--verbose": True,
                        },
                    )
                    self.assertEqual(result.success, True, cpv)
                    self.assertEqual(
                        self._merge_list_use(result.depgraph, cpv), use_str, cpv
                    )
            finally:
                playground.cleanup()

    def testMaskedUseDisplayRequiredUse(self):
        """
        The message for unmet REQUIRED_USE also shows MASKED_USE flags
        separately.
        """
        py = "python_single_target_python3_"
        ebuilds = {
            "dev-libs/z-1": {
                "EAPI": "10-pre",
                "IUSE": f"python {py}12 {py}13",
                "MASKED_USE": f"!python? ( {py}12 {py}13 )",
                "REQUIRED_USE": f"^^ ( {py}12 {py}13 )",
            },
        }
        user_config = {"make.conf": ('USE_EXPAND="PYTHON_SINGLE_TARGET"',)}
        playground = ResolverPlayground(ebuilds=ebuilds, user_config=user_config)
        try:
            result = playground.run(["dev-libs/z"], options={"--pretend": True})
            self.assertEqual(result.success, False)
            havecolor = portage.output.havecolor
            noiselimit = portage.util.noiselimit
            portage.output.havecolor = 0
            portage.util.noiselimit = 0
            stderr = io.StringIO()
            try:
                with contextlib.redirect_stderr(stderr):
                    result.depgraph.display_problems()
            finally:
                portage.output.havecolor = havecolor
                portage.util.noiselimit = noiselimit
            self.assertIn(
                '- dev-libs/z-1::test_repo USE="-python" '
                'MASKED_USE="-python => PYTHON_SINGLE_TARGET"\n',
                stderr.getvalue(),
            )
        finally:
            playground.cleanup()

    @staticmethod
    def _merge_list_use(depgraph, cpv):
        """Return the USE strings of cpv in the merge list, without color"""
        havecolor = portage.output.havecolor
        noiselimit = portage.util.noiselimit
        portage.output.havecolor = 0
        portage.util.noiselimit = 0
        stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout):
                depgraph.display(depgraph._dynamic_config._serialized_tasks_cache)
        finally:
            portage.output.havecolor = havecolor
            portage.util.noiselimit = noiselimit
        for line in stdout.getvalue().splitlines():
            if f"] {cpv}" in line:
                line = line.split(f"{cpv}::test_repo", 1)[1]
                # Drop the download size at the end.
                return line.rsplit(" ", 2)[0].strip()
        raise AssertionError(f"{cpv} not in merge list:\n{stdout.getvalue()}")
