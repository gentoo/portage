# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
    ResolverPlayground,
    ResolverPlaygroundTestCase,
)
from portage.util.digraph import digraph

from _emerge.DepPriority import DepPriority
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
                circular_dependency_message=["USE=harfbuzz"],
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
                circular_dependency_message=["USE=system-b"],
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
                "USE=doc nls" in result.circular_dependency_message,
                result.circular_dependency_message,
            )
        finally:
            playground.cleanup()
