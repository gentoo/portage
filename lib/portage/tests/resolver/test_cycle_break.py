# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import contextlib
import copy
import io

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)

from _emerge.create_depgraph_params import create_depgraph_params
from _emerge.depgraph import resume_depgraph
from _emerge.Package import Package

FREETYPE = {
    "DEPEND": "harfbuzz? ( media-libs/harfbuzz )",
    "IUSE": "+harfbuzz",
    "EAPI": "8",
}

HARFBUZZ = {
    "DEPEND": "media-libs/freetype",
    "EAPI": "8",
}

CYCLE = {
    "media-libs/freetype-1": FREETYPE,
    "media-libs/harfbuzz-1": HARFBUZZ,
}

# dev-lang/mono needs dev-dotnet/libgdiplus with USE=-minimal, while
# libgdiplus needs mono to build.
MONO = {
    "dev-lang/mono-1": {
        "DEPEND": "!minimal? ( dev-dotnet/libgdiplus )",
        "IUSE": "minimal",
        "EAPI": "8",
    },
    "dev-dotnet/libgdiplus-1": {
        "BDEPEND": "dev-lang/mono",
        "EAPI": "8",
    },
}

USE_HARFBUZZ = {"make.conf": ('USE="harfbuzz"',)}

HARFBUZZ_SOLUTION = frozenset([frozenset([("harfbuzz", False)])])


class CycleBreakTestCase(TestCase):
    """
    With --cycle-break=y, a cycle that cannot be solved otherwise is
    broken by building one of the packages twice: first with the USE
    flag that closes the cycle changed, and then as requested.
    """

    def _run(self, test_cases, ebuilds, **kwargs):
        playground = ResolverPlayground(ebuilds=copy.deepcopy(ebuilds), **kwargs)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testFreetypeHarfbuzz(self):
        # The user asked for USE=harfbuzz, so the cycle cannot be solved
        # with a USE change.
        test_cases = (
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                options={"--cycle-break": "y"},
                success=True,
                mergelist=[
                    "[cycle-break]media-libs/freetype-1",
                    "media-libs/harfbuzz-1",
                    "media-libs/freetype-1",
                ],
            ),
            # Disabled by default.
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                success=False,
                circular_dependency_solutions={
                    "media-libs/harfbuzz-1": HARFBUZZ_SOLUTION
                },
            ),
        )
        self._run(test_cases, CYCLE, user_config=USE_HARFBUZZ)

    def testReverseDependencies(self):
        """
        Packages outside of the cycle that depend on the package built
        twice are merged after its final build, and are never satisfied
        by the transient build.
        """
        ebuilds = {
            **CYCLE,
            "app-misc/foo-1": {
                "DEPEND": "media-libs/freetype[harfbuzz]",
                "EAPI": "8",
            },
            "app-misc/bar-1": {"RDEPEND": "media-libs/freetype", "EAPI": "8"},
        }
        test_cases = (
            ResolverPlaygroundTestCase(
                [atom],
                options={"--cycle-break": "y"},
                success=True,
                mergelist=[
                    "[cycle-break]media-libs/freetype-1",
                    "media-libs/harfbuzz-1",
                    "media-libs/freetype-1",
                    f"{atom}-1",
                ],
            )
            for atom in ("app-misc/foo", "app-misc/bar")
        )
        self._run(test_cases, ebuilds, user_config=USE_HARFBUZZ)

    def testDefaultUse(self):
        """
        A flag enabled by an IUSE default could be disabled for good
        with an autounmask USE change, but --cycle-break=y builds the
        package twice instead.
        """
        test_cases = (
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                options={"--cycle-break": "y"},
                success=True,
                mergelist=[
                    "[cycle-break]media-libs/freetype-1",
                    "media-libs/harfbuzz-1",
                    "media-libs/freetype-1",
                ],
            ),
        )
        self._run(test_cases, CYCLE)

    def testNoUnnecessaryCycleBreak(self):
        ebuilds = {
            "dev-libs/A-1": {"DEPEND": "dev-libs/B", "EAPI": "8"},
            "dev-libs/B-1": {"EAPI": "8"},
        }
        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--cycle-break": "y"},
                success=True,
                mergelist=["dev-libs/B-1", "dev-libs/A-1"],
            ),
        )
        self._run(test_cases, ebuilds)

    def testSelfBuildDependency(self):
        """
        A package that needs itself to build with some flag enabled is
        built once without the flag first.
        """
        ebuilds = {
            "dev-lang/rust-2": {
                "BDEPEND": "system-bootstrap? ( dev-lang/rust )",
                "IUSE": "+system-bootstrap",
                "EAPI": "8",
            },
        }
        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-lang/rust"],
                options={"--cycle-break": "y"},
                success=True,
                mergelist=[
                    "[cycle-break]dev-lang/rust-2",
                    "dev-lang/rust-2",
                ],
            ),
        )
        self._run(
            test_cases,
            ebuilds,
            user_config={"make.conf": ('USE="system-bootstrap"',)},
        )

    def testParentUseDep(self):
        """
        No transient build is scheduled when a parent needs the flag
        that it would disable.
        """
        ebuilds = {
            **CYCLE,
            "media-libs/harfbuzz-1": {
                **HARFBUZZ,
                "DEPEND": "media-libs/freetype[harfbuzz]",
            },
        }
        test_cases = (
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                options={"--cycle-break": "y"},
                success=False,
                circular_dependency_solutions={},
            ),
        )
        self._run(test_cases, ebuilds, user_config=USE_HARFBUZZ)

    def testCycleThroughOtherChild(self):
        """
        The transient build is not used when it still depends on the
        cycle through a dependency that the USE change does not drop, and
        the original cycle is reported.

        Here freetype needs harfbuzz both directly with USE=harfbuzz and
        through dev-libs/X. Building freetype with USE=-harfbuzz first
        would drop only the direct dependency, so the transient build
        would still need harfbuzz, which needs freetype.
        """
        ebuilds = {
            **CYCLE,
            "media-libs/freetype-1": {
                **FREETYPE,
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz ) dev-libs/X",
            },
            "dev-libs/X-1": {
                "DEPEND": "media-libs/harfbuzz",
                "EAPI": "8",
            },
        }
        test_cases = (
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                options={"--cycle-break": "y"},
                success=False,
                circular_dependency_solutions={
                    "media-libs/harfbuzz-1": HARFBUZZ_SOLUTION
                },
            ),
        )
        self._run(test_cases, ebuilds, user_config=USE_HARFBUZZ)

    def testHint(self):
        """
        Without --cycle-break=y, the circular dependency error suggests
        it when it might help.
        """
        hint = "Alternatively, emerge --cycle-break=y might build"

        def problems(ebuilds, options):
            playground = ResolverPlayground(
                ebuilds=copy.deepcopy(ebuilds), user_config=USE_HARFBUZZ
            )
            try:
                result = playground.run(["media-libs/harfbuzz"], options=options)
                self.assertFalse(result.success)
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result.depgraph.display_problems()
                return stderr.getvalue()
            finally:
                playground.cleanup()

        output = problems(CYCLE, {"--cycle-break": "n"})
        self.assertIn(hint, output)
        self.assertIn(
            'media-libs/freetype-1 twice,\nfirst with USE="-harfbuzz"', output
        )

        # Not when --cycle-break=y has already failed.
        ebuilds = {
            **CYCLE,
            "media-libs/freetype-1": {
                **FREETYPE,
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz ) dev-libs/X",
            },
            "dev-libs/X-1": {
                "DEPEND": "media-libs/harfbuzz",
                "EAPI": "8",
            },
        }
        output = problems(ebuilds, {"--cycle-break": "y"})
        self.assertIn("circular dependencies", output)
        self.assertNotIn(hint, output)

    def testHintEnabledFlag(self):
        """
        The hint shows a flag that the first build enables as enabled.
        Since autounmask breaks such a cycle with a USE change before the
        circular dependency error is shown, the autounmask output says
        that the USE change only breaks a cycle and suggests
        --cycle-break=y as well.
        """
        hint = (
            "Alternatively, emerge --cycle-break=y might build dev-lang/mono-1 "
            'twice,\nfirst with USE="minimal" and then as requested.'
        )
        note = "The USE change for dev-lang/mono-1 only breaks a circular dependency."

        def problems(options):
            playground = ResolverPlayground(ebuilds=copy.deepcopy(MONO))
            try:
                result = playground.run(["dev-lang/mono"], options=options)
                self.assertFalse(result.success)
                # The playground has displayed the problems already.
                result.depgraph._dynamic_config._displayed_autounmask = False
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result.depgraph.display_problems()
                return stderr.getvalue()
            finally:
                playground.cleanup()

        output = problems({"--autounmask": "n"})
        self.assertIn("circular dependencies", output)
        self.assertIn(hint, output)

        output = problems({})
        self.assertIn(">=dev-lang/mono-1 minimal", output)
        self.assertIn(note, output)
        self.assertIn(hint, output)

    def testHintNotForAutounmask(self):
        """
        The autounmask output does not suggest --cycle-break=y when it
        could not use the USE change, here because the enabled flag pulls
        in another dependency.
        """
        ebuilds = {
            **CYCLE,
            "media-libs/freetype-1": {
                "DEPEND": (
                    "!bootstrap? ( media-libs/harfbuzz ) bootstrap? ( dev-libs/Y )"
                ),
                "IUSE": "bootstrap",
                "EAPI": "8",
            },
            "dev-libs/Y-1": {"EAPI": "8"},
        }
        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            result = playground.run(["media-libs/harfbuzz"])
            self.assertFalse(result.success)
            self.assertEqual(
                result.use_changes, {"media-libs/freetype-1": {"bootstrap": True}}
            )
            # The playground has displayed the problems already.
            result.depgraph._dynamic_config._displayed_autounmask = False
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result.depgraph.display_problems()
            output = stderr.getvalue()
        finally:
            playground.cleanup()
        self.assertIn(">=media-libs/freetype-1 bootstrap", output)
        self.assertNotIn("--cycle-break", output)

    def testEnabledFlag(self):
        """
        A cycle that is only broken by enabling a flag that pulls in
        another dependency is not solved with a transient build, since
        that dependency is not in the graph.
        """
        ebuilds = {
            **CYCLE,
            "media-libs/freetype-1": {
                "DEPEND": (
                    "!bootstrap? ( media-libs/harfbuzz ) bootstrap? ( dev-libs/Y )"
                ),
                "IUSE": "bootstrap",
                "EAPI": "8",
            },
            "dev-libs/Y-1": {"EAPI": "8"},
        }
        test_cases = (
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                options={"--cycle-break": "y"},
                success=False,
                use_changes={"media-libs/freetype-1": {"bootstrap": True}},
            ),
        )
        self._run(test_cases, ebuilds)

    def testEnabledFlagDropsDependency(self):
        """
        A cycle that is broken by enabling a flag is solved with a
        transient build when the flag only drops dependencies, like
        dev-lang/mono, which needs dev-dotnet/libgdiplus with USE=-minimal
        while libgdiplus needs mono to build.
        """
        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-lang/mono"],
                options={"--cycle-break": "y"},
                success=True,
                mergelist=[
                    "[cycle-break]dev-lang/mono-1",
                    "dev-dotnet/libgdiplus-1",
                    "dev-lang/mono-1",
                ],
            ),
            ResolverPlaygroundTestCase(
                ["dev-lang/mono"],
                options={"--cycle-break": "y", "--autounmask": "n"},
                success=True,
                mergelist=[
                    "[cycle-break]dev-lang/mono-1",
                    "dev-dotnet/libgdiplus-1",
                    "dev-lang/mono-1",
                ],
            ),
        )
        self._run(test_cases, MONO)

    def testEnabledFlagChangesUseDep(self):
        """
        A cycle that is broken by enabling a flag is not solved with a
        transient build when the flag changes a USE dependency, since the
        transient build would need dev-libs/Y[bootstrap] and the graph
        only has dev-libs/Y with USE=-bootstrap.
        """
        ebuilds = {
            **CYCLE,
            "media-libs/freetype-1": {
                "DEPEND": (
                    "!bootstrap? ( media-libs/harfbuzz ) dev-libs/Y[bootstrap?]"
                ),
                "IUSE": "bootstrap",
                "EAPI": "8",
            },
            "dev-libs/Y-1": {"IUSE": "bootstrap", "EAPI": "8"},
        }
        test_cases = (
            ResolverPlaygroundTestCase(
                ["media-libs/harfbuzz"],
                options={"--cycle-break": "y", "--autounmask": "n"},
                success=False,
                circular_dependency_solutions={
                    "media-libs/harfbuzz-1": frozenset(
                        [frozenset([("bootstrap", True)])]
                    )
                },
            ),
        )
        self._run(test_cases, ebuilds)

    def testLimit(self):
        """
        Make sure we honor the _max_cycle_breaks limit: no more than
        three packages are built twice in one run.
        """
        ebuilds = {}
        for i in range(1, 5):
            ebuilds[f"media-libs/a{i}-1"] = {
                "DEPEND": f"x? ( media-libs/b{i} )",
                "IUSE": "+x",
                "EAPI": "8",
            }
            ebuilds[f"media-libs/b{i}-1"] = {
                "DEPEND": f"media-libs/a{i}",
                "EAPI": "8",
            }
        test_cases = (
            ResolverPlaygroundTestCase(
                [f"media-libs/b{i}" for i in range(1, 4)],
                options={"--cycle-break": "y"},
                success=True,
                ambiguous_merge_order=True,
                mergelist=[
                    tuple(
                        pkg
                        for i in range(1, 4)
                        for pkg in (
                            f"[cycle-break]media-libs/a{i}-1",
                            f"media-libs/b{i}-1",
                            f"media-libs/a{i}-1",
                        )
                    )
                ],
            ),
            ResolverPlaygroundTestCase(
                [f"media-libs/b{i}" for i in range(1, 5)],
                options={"--cycle-break": "y"},
                success=False,
                circular_dependency_solutions={
                    "media-libs/b4-1": frozenset([frozenset([("x", False)])])
                },
            ),
        )
        self._run(test_cases, ebuilds, user_config={"make.conf": ('USE="x"',)})

    def testResume(self):
        """
        The resume list keeps the transient build until it is merged.
        """
        installed = {"media-libs/freetype-1": {**FREETYPE, "USE": ""}}

        def resume(playground, mergelist, nodeps=False):
            myopts = {"--cycle-break": "y"}
            if nodeps:
                myopts["--nodeps"] = True
            entries = [["ebuild", playground.eroot, cpv, "merge"] for cpv in mergelist]
            mtimedb = {
                "resume": {
                    "favorites": ["media-libs/harfbuzz"],
                    "mergelist": entries,
                    "cycle_break": [
                        [playground.eroot, "media-libs/freetype-1", {"harfbuzz": False}]
                    ],
                }
            }
            myparams = create_depgraph_params(myopts, None)
            success, mydepgraph, _dropped_tasks = resume_depgraph(
                playground.settings,
                playground.trees,
                mtimedb,
                myopts,
                myparams,
                None,
            )
            self.assertTrue(success)
            return [
                (x.cpv, bool(x.cycle_use_changes))
                for x in mydepgraph.altlist()
                if isinstance(x, Package)
            ]

        full_mergelist = [
            "media-libs/freetype-1",
            "media-libs/harfbuzz-1",
            "media-libs/freetype-1",
        ]
        expected = [
            ("media-libs/freetype-1", True),
            ("media-libs/harfbuzz-1", False),
            ("media-libs/freetype-1", False),
        ]

        # All resume lists are loaded in one process, as with
        # --keep-going.
        playground = ResolverPlayground(
            ebuilds=copy.deepcopy(CYCLE),
            installed=installed,
            user_config=USE_HARFBUZZ,
        )
        try:
            # Nothing has been merged yet.
            self.assertEqual(resume(playground, full_mergelist), expected)
            # Without a graph, the merge list order is kept.
            self.assertEqual(resume(playground, full_mergelist, nodeps=True), expected)
            # The transient build has been merged.
            self.assertEqual(
                resume(playground, full_mergelist[1:]),
                expected[1:],
            )
        finally:
            playground.cleanup()
