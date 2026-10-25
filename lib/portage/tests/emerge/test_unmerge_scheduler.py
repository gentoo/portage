# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import tempfile
import types

from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop

from _emerge.UnmergeScheduler import UnmergeScheduler, _symlink_deps


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

    def test_symlink_deps(self):
        """
        The owner of a symlink to a directory waits for the packages with
        files beneath it, unless they already wait for it.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            real = os.path.join(tmpdir, "real")
            link = os.path.join(tmpdir, "link")
            os.mkdir(real)
            os.symlink("real", link)
            contents = {
                "A": {link: ("sym",)},
                "B": {os.path.join(link, "x"): ("obj",)},
                "C": {os.path.join(link, "y"): ("obj",)},
                "D": {os.path.join(link, "z"): ("obj",)},
                "E": {os.path.join(real, "w"): ("obj",)},
            }
            vardb = types.SimpleNamespace(
                _dblink=lambda cpv: types.SimpleNamespace(
                    getcontents=lambda: contents[cpv]
                )
            )
            deps = {"B": {"A"}, "D": {"X"}, "X": {"A"}}
            self.assertEqual(
                _symlink_deps(vardb, ["A", "B", "C", "D", "E"], deps),
                {"A": {"C"}, "B": {"A"}, "D": {"X"}, "X": {"A"}},
            )
