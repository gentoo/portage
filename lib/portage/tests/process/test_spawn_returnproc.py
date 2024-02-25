# Copyright 2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import signal

from portage.process import find_binary, spawn
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop


class SpawnReturnProcTestCase(TestCase):
    def testSpawnReturnProcWait(self):
        true_binary = find_binary("true")
        self.assertNotEqual(true_binary, None)

        loop = global_event_loop()

        async def watch_pid():
            proc = spawn([true_binary], returnproc=True)
            self.assertEqual(await proc.wait(), os.EX_OK)

            # A second wait should also work.
            self.assertEqual(await proc.wait(), os.EX_OK)

        loop.run_until_complete(watch_pid())

    def testSpawnReturnProcTerminate(self):
        sleep_binary = find_binary("sleep")
        self.assertNotEqual(sleep_binary, None)

        loop = global_event_loop()

        async def watch_pid():
            proc = spawn([sleep_binary, "9999"], returnproc=True)
            proc.terminate()
            self.assertEqual(await proc.wait(), -signal.SIGTERM)

        loop.run_until_complete(watch_pid())
