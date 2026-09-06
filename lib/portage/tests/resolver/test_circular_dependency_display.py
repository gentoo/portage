# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
import json
from contextlib import redirect_stdout

from portage.output import blue, red
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.util.digraph import digraph

from _emerge.DepPriority import DepPriority
from _emerge.main import parse_opts
from _emerge.resolver.circular_dependency import circular_dependency_handler


class CircularDependencyDisplayTestCase(TestCase):
    """
    Verify that the circular dependency handler is always able to
    describe the cycle it was created for, even when the cycle consists
    entirely of dependencies that are ignored by the default
    ignore_priority (bug 929010).
    """

    def _handler(self, graph):
        # The message preparation code does not need a depgraph, so
        # avoid the cost of constructing one here.
        handler = circular_dependency_handler.__new__(circular_dependency_handler)
        handler.graph = graph
        handler.depgraph = None
        handler.all_parent_atoms = {}
        handler.cycles, handler.shortest_cycle = handler._find_cycles()
        return handler

    def testRuntimePostCycle(self):
        # PDEPEND edges are ignored by ignore_medium_soft.
        graph = digraph()
        priority = DepPriority(runtime_post=True)
        graph.add("B", "A", priority=priority)
        graph.add("A", "B", priority=priority)

        handler = self._handler(graph)
        self.assertNotEqual(handler.shortest_cycle, None)
        self.assertEqual(set(handler.shortest_cycle), {"A", "B"})

        message = handler._prepare_circular_dep_message()
        self.assertNotEqual(message, None)
        self.assertTrue("A" in message)
        self.assertTrue("B" in message)

    def testOptionalCycle(self):
        # Optional edges are ignored by every ignore_priority.
        graph = digraph()
        priority = DepPriority(optional=True)
        graph.add("B", "A", priority=priority)
        graph.add("A", "B", priority=priority)

        handler = self._handler(graph)
        self.assertNotEqual(handler.shortest_cycle, None)
        self.assertNotEqual(handler._prepare_circular_dep_message(), None)

    def testBuildtimeCycle(self):
        # The common case still uses the default ignore_priority.
        graph = digraph()
        priority = DepPriority(buildtime=True)
        graph.add("B", "A", priority=priority)
        graph.add("A", "B", priority=priority)

        handler = self._handler(graph)
        self.assertEqual(set(handler.shortest_cycle), {"A", "B"})


class CircularDependencyUseDisplayTestCase(TestCase):
    """
    The reported cycle names the USE flags that pull in each dependency
    (bug 310613).
    """

    def testUseFlagInCycleMessage(self):
        ebuilds = {
            "media-libs/freetype-1": {
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "IUSE": "+harfbuzz",
                "EAPI": "8",
            },
            "media-libs/harfbuzz-1": {
                "DEPEND": "media-libs/freetype",
                "EAPI": "8",
            },
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["media-libs/freetype"],
                success=False,
                circular_dependency_message=[f"USE={red('harfbuzz')}"],
                circular_dependency_solutions={
                    "media-libs/harfbuzz-1": frozenset(
                        [frozenset([("harfbuzz", False)])]
                    )
                },
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testNegatedUseFlagInCycleMessage(self):
        # The flag is disabled, and disabling it is what pulls the
        # dependency in, so enabling it is the way out of the cycle.
        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": "!system-b? ( dev-libs/B )",
                "IUSE": "system-b",
                "EAPI": "8",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/A",
                "EAPI": "8",
            },
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                # Without this, a resolver that is able to apply the USE
                # change itself would never report the cycle.
                options={"--autounmask-use": "n"},
                success=False,
                circular_dependency_message=[f"USE={blue('-system-b')}"],
                circular_dependency_solutions={
                    "dev-libs/B-1": frozenset([frozenset([("system-b", True)])])
                },
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testUnrelatedUseFlagNotReported(self):
        # unrelated? ( ) encloses the dependency, but the dependency is
        # pulled in unconditionally as well, so the flag is not to blame.
        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": "unrelated? ( dev-libs/B ) dev-libs/B",
                "IUSE": "+unrelated",
                "EAPI": "8",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/A",
                "EAPI": "8",
            },
        }

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            result = playground.run(["dev-libs/A"])
            self.assertEqual(result.success, False)
            self.assertTrue(
                "USE=" not in result.circular_dependency_message,
                result.circular_dependency_message,
            )
        finally:
            playground.cleanup()

    def testSeveralUseFlagsInCycleMessage(self):
        # No single flag removes the dependency, but the two of them
        # together do, so both are to blame.
        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": "doc? ( dev-libs/B ) nls? ( dev-libs/B )",
                "IUSE": "+doc +nls",
                "EAPI": "8",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/A",
                "EAPI": "8",
            },
        }

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            result = playground.run(["dev-libs/A"], options={"--autounmask-use": "n"})
            self.assertEqual(result.success, False)
            self.assertTrue(
                f"USE={red('doc')} {red('nls')}" in result.circular_dependency_message,
                result.circular_dependency_message,
            )
        finally:
            playground.cleanup()


class CircularTestDependencyTestCase(TestCase):
    """
    Cycles caused by test dependencies are identified as such, so that
    the user can be pointed at FEATURES=test instead of a USE change
    that FEATURES=test would have to be disabled for anyway
    (bug 416871, bug 703348).
    """

    def testTestDepCycle(self):
        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": "test? ( dev-libs/B )",
                "IUSE": "test",
                "EAPI": "8",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/A",
                "EAPI": "8",
            },
        }

        user_config = {
            "make.conf": ('USE="test"',),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                success=False,
                circular_dependency_test_parents=["dev-libs/A-1"],
                circular_dependency_solutions={
                    "dev-libs/B-1": frozenset([frozenset([("test", False)])])
                },
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds, user_config=user_config)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testTestDepCycleWithAnotherFlag(self):
        # A second flag pulls in the same dependency, so disabling
        # FEATURES=test alone does not break the cycle. The package is
        # still worth naming, since the test suite is the part the user
        # can most easily do without.
        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": "test? ( dev-libs/B ) doc? ( dev-libs/B )",
                "IUSE": "test doc",
                "EAPI": "8",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/A",
                "EAPI": "8",
            },
        }

        user_config = {
            "make.conf": ('USE="test doc"',),
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--autounmask-use": "n"},
                success=False,
                circular_dependency_test_parents=["dev-libs/A-1"],
                circular_dependency_solutions={
                    "dev-libs/B-1": frozenset(
                        [frozenset([("doc", False), ("test", False)])]
                    )
                },
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds, user_config=user_config)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()


class CircularMaskedAlternativeTestCase(TestCase):
    """
    A bootstrap package that is not keyworded is never considered for a
    || ( ) choice, because those are evaluated with autounmask disabled.
    Report it as a way out of the resulting cycle (bug 971256).
    """

    def testMaskedBootstrapAlternative(self):
        ebuilds = {
            "dev-lang/go-2": {
                "BDEPEND": "|| ( dev-lang/go dev-lang/go-bootstrap )",
                "EAPI": "8",
            },
            "dev-lang/go-bootstrap-1": {
                "EAPI": "8",
                "KEYWORDS": "",
            },
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-lang/go"],
                success=False,
                circular_dependency_masked_alternatives=["dev-lang/go-bootstrap-1"],
                circular_dependency_solutions={},
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testUseDependencyAlternative(self):
        # The cycle member is pulled in by an atom with a conditional
        # USE dependency, which the || ( ) group has to be matched
        # against in its unevaluated form.
        ebuilds = {
            "dev-lang/go-2": {
                "BDEPEND": "|| ( dev-lang/go[cgo?] dev-lang/go-bootstrap )",
                "IUSE": "+cgo",
                "EAPI": "8",
            },
            "dev-lang/go-bootstrap-1": {
                "EAPI": "8",
                "KEYWORDS": "",
            },
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-lang/go"],
                success=False,
                circular_dependency_masked_alternatives=["dev-lang/go-bootstrap-1"],
                circular_dependency_solutions={},
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()


class CircularSearchTruncatedTestCase(TestCase):
    """
    The search for USE changes is limited, because the number of
    combinations is exponential in the number of flags. Say so instead
    of reporting that no solution exists.
    """

    def testSearchTruncated(self):
        flags = [f"flag{i}" for i in range(12)]
        dep = " ".join(f"{flag}? ( dev-libs/B )" for flag in flags)

        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": dep,
                "IUSE": " ".join(f"+{flag}" for flag in flags),
                "EAPI": "8",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/A",
                "EAPI": "8",
            },
        }

        test_cases = (
            ResolverPlaygroundTestCase(
                ["dev-libs/A"],
                options={"--autounmask-use": "n"},
                success=False,
                circular_dependency_solutions={},
                circular_dependency_search_truncated=["dev-libs/A-1"],
            ),
        )

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            for test_case in test_cases:
                playground.run_TestCase(test_case)
                self.assertEqual(test_case.test_success, True, test_case.fail_msg)
        finally:
            playground.cleanup()

    def testMaxUseFlagsRaised(self):
        # PORTAGE_CIRCULAR_MAX_USE_FLAGS is high enough to cover the 12
        # flags, so the search runs and finds a solution.
        flags = [f"flag{i}" for i in range(12)]
        dep = " ".join(f"{flag}? ( dev-libs/B )" for flag in flags)

        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": dep,
                "IUSE": " ".join(f"+{flag}" for flag in flags),
                "EAPI": "8",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/A",
                "EAPI": "8",
            },
        }

        user_config = {
            "make.conf": ('PORTAGE_CIRCULAR_MAX_USE_FLAGS="16"',),
        }

        playground = ResolverPlayground(ebuilds=ebuilds, user_config=user_config)
        try:
            result = playground.run(["dev-libs/A"], options={"--autounmask-use": "n"})
            self.assertEqual(result.success, False)
            self.assertEqual(result.circular_dependency_search_truncated, set())
            self.assertNotEqual(result.circular_dependency_solutions, {})
        finally:
            playground.cleanup()


class CircularDependencyJsonReportTestCase(TestCase):
    """
    --circular-deps-report=json describes the cycle in a form that
    automated consumers can parse.
    """

    def testJsonReport(self):
        ebuilds = {
            "media-libs/freetype-1": {
                "DEPEND": "harfbuzz? ( media-libs/harfbuzz )",
                "IUSE": "+harfbuzz",
                "EAPI": "8",
            },
            "media-libs/harfbuzz-1": {
                "DEPEND": "media-libs/freetype",
                "EAPI": "8",
            },
        }

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            result = playground.run(
                ["media-libs/freetype"], options={"--circular-deps-report": "json"}
            )
            self.assertEqual(result.success, False)

            output = io.StringIO()
            with redirect_stdout(output):
                result.depgraph.display_problems()
            report = json.loads(output.getvalue())

            self.assertEqual(
                {edge["parent"] for edge in report["shortest_cycle"]},
                {"media-libs/freetype-1", "media-libs/harfbuzz-1"},
            )
            self.assertTrue(
                any(
                    edge["affecting_use"] == ["harfbuzz"]
                    for edge in report["shortest_cycle"]
                )
            )
            # The flag belongs to freetype, which is the package the
            # change has to be applied to, not to harfbuzz, which is the
            # package the change gets rid of the dependency on.
            self.assertEqual(
                report["solutions"],
                [
                    {
                        "package": "media-libs/freetype-1",
                        "use_changes": [{"harfbuzz": False}],
                    }
                ],
            )
            self.assertEqual(report["search_truncated"], [])
            self.assertEqual(report["max_affecting_use"], 10)
        finally:
            playground.cleanup()

    def testDefaultFormat(self):
        # Without a format, the option selects the text report rather
        # than failing to parse.
        opts = parse_opts(["--circular-deps-report", "dev-libs/A"], silent=True)[1]
        self.assertNotEqual(opts.get("--circular-deps-report"), "json")

    def testJsonReportSearchTruncated(self):
        flags = [f"flag{i}" for i in range(12)]
        dep = " ".join(f"{flag}? ( dev-libs/B )" for flag in flags)

        ebuilds = {
            "dev-libs/A-1": {
                "DEPEND": dep,
                "IUSE": " ".join(f"+{flag}" for flag in flags),
                "EAPI": "8",
            },
            "dev-libs/B-1": {
                "DEPEND": "dev-libs/A",
                "EAPI": "8",
            },
        }

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            result = playground.run(
                ["dev-libs/A"],
                options={"--circular-deps-report": "json", "--autounmask-use": "n"},
            )
            self.assertEqual(result.success, False)

            output = io.StringIO()
            with redirect_stdout(output):
                result.depgraph.display_problems()
            report = json.loads(output.getvalue())

            self.assertEqual(report["solutions"], [])
            self.assertEqual(report["search_truncated"], ["dev-libs/A-1"])
        finally:
            playground.cleanup()
