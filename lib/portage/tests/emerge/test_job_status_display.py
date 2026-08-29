# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import contextlib
import io

from _emerge.JobStatusDisplay import JobStatusDisplay
from portage.tests import TestCase


class JobStatusDisplayTestCase(TestCase):
    def test_display_message(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            display = JobStatusDisplay()
            display.displayMessage("formatted message")
            display.displayMessage("another formatted message", raw=False)
            display.displayMessage("raw message", raw=True)

        output = buf.getvalue()
        self.assertIn(">>> formatted message\n", output)
        self.assertIn(">>> another formatted message\n", output)
        self.assertIn("raw message\n", output)
        self.assertNotIn(">>> raw message\n", output)
