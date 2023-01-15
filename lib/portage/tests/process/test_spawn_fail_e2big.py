# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import platform
import tempfile

from pathlib import Path

import portage.process

from portage import shutil
from portage.const import BASH_BINARY
from portage.tests import TestCase


class SpawnE2bigTestCase(TestCase):
    def testSpawnE2big(self):
        if platform.system() != "Linux":
            self.skipTest("not Linux")

        env = dict()
        env["VERY_LARGE_ENV_VAR"] = "X" * 1024 * 256

        tmpdir = tempfile.mkdtemp()
        try:
            logfile = tmpdir / Path("logfile")
            echo_output = "Should never appear"
            retval = portage.process.spawn(
                [BASH_BINARY, "-c", "echo", echo_output], env=env, logfile=logfile
            )

            with open(logfile) as f:
                logfile_content = f.read()
                self.assertIn(
                    "Largest environment variable: VERY_LARGE_ENV_VAR (262164 bytes)",
                    logfile_content,
                )
            self.assertEqual(retval, 1)
        finally:
            shutil.rmtree(tmpdir)
