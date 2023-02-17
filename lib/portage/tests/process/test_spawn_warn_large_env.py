# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import platform
import tempfile

from pathlib import Path

import portage.process

from portage import shutil
from portage.tests import TestCase


class SpawnWarnLargeEnvTestCase(TestCase):
    def testSpawnWarnLargeEnv(self):
        if platform.system() != "Linux":
            self.skipTest("not Linux")

        env = dict()
        env["LARGE_ENV_VAR"] = "X" * 1024 * 96

        tmpdir = tempfile.mkdtemp()
        previous_env_too_large_warnings = portage.process.env_too_large_warnings
        try:
            logfile = tmpdir / Path("logfile")
            echo_output = "This is an echo process with a large env"
            retval = portage.process.spawn(
                ["echo", echo_output],
                env=env,
                logfile=logfile,
                warn_on_large_env=True,
            )

            with open(logfile) as f:
                logfile_content = f.read()
                self.assertIn(
                    echo_output,
                    logfile_content,
                )
            self.assertTrue(
                portage.process.env_too_large_warnings > previous_env_too_large_warnings
            )
            self.assertEqual(retval, 0)
        finally:
            shutil.rmtree(tmpdir)
