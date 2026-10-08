# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
from contextlib import redirect_stderr

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground


class BacktrackRestartCausesTestCase(TestCase):
    def _display_problems(self, result):
        output = io.StringIO()
        with redirect_stderr(output):
            result.depgraph.display_problems()
        return output.getvalue()

    def testBacktrackRestartCauses(self):
        ebuilds = {
            "app-misc/A-1": {"EAPI": "8", "RDEPEND": "=dev-libs/C-1"},
            "app-misc/B-1": {"EAPI": "8", "RDEPEND": "=dev-libs/C-2"},
            "dev-libs/C-1": {"EAPI": "8"},
            "dev-libs/C-2": {"EAPI": "8"},
            "dev-libs/D-1": {"EAPI": "8"},
        }

        playground = ResolverPlayground(ebuilds=ebuilds)
        try:
            # A and B can not be installed together.
            result = playground.run(
                ["app-misc/A", "app-misc/B"], options={"--backtrack": 5}
            )
            self.assertEqual(result.success, False)
            output = self._display_problems(result)
            self.assertIn("Backtracking did not find a solution in 4 attempts", output)
            self.assertIn("  dev-libs/C (3 attempts)\n", output)
            self.assertIn("    slot conflict for dev-libs/C:0 (1 attempt)\n", output)
            self.assertIn(
                "    =dev-libs/C-1 required by app-misc/A-1 is unsatisfied (1 attempt)\n",
                output,
            )
            self.assertIn(
                "    =dev-libs/C-2 required by app-misc/B-1 is unsatisfied (1 attempt)\n",
                output,
            )

            # Backtracking disabled.
            result = playground.run(
                ["app-misc/A", "app-misc/B"], options={"--backtrack": 0}
            )
            self.assertEqual(result.success, False)
            self.assertNotIn(
                "Backtracking did not find a solution",
                self._display_problems(result),
            )

            # Success.
            result = playground.run(["dev-libs/D"])
            self.assertEqual(result.success, True)
            self.assertNotIn(
                "Backtracking did not find a solution",
                self._display_problems(result),
            )
        finally:
            playground.cleanup()
