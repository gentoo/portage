# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop

from _emerge.UnmergeScheduler import UnmergeScheduler


class UnmergeSchedulerTestCase(TestCase):
    def test_prerequisites(self):
        """
        A package waits for the packages that must be unmerged before it,
        and through a package that is not being unmerged, for the ones
        that it waits for in turn.
        """
        deps = {"B": {"A"}, "X": {"B"}, "C": {"X", "D"}, "E": {"D"}}
        scheduler = UnmergeScheduler(
            None,
            {},
            None,
            ["A", "D", "E", "C"],
            deps,
            None,
            None,
            event_loop=global_event_loop(),
        )
        self.assertEqual(
            scheduler._waiting,
            {"A": set(), "D": set(), "E": {"D"}, "C": {"A", "D"}},
        )
        self.assertEqual(list(scheduler._ready), ["A", "D"])
