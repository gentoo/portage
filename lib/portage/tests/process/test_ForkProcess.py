# Copyright 2023-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import functools
import tempfile
from unittest.mock import patch

from portage import multiprocessing, os
from portage.tests import TestCase
from portage.util._async.ForkProcess import ForkProcess
from portage.util.futures import asyncio


class ForkProcessTestCase(TestCase):
    @staticmethod
    def _test_spawn_logfile(logfile, target):
        multiprocessing.set_start_method("spawn", force=True)
        loop = asyncio._wrap_loop()
        proc = ForkProcess(scheduler=loop, target=target, logfile=logfile)
        proc.start()
        return proc.wait()

    def test_spawn_logfile(self):
        """
        Test logfile with multiprocessing spawn start method.
        """
        test_string = "hello world"
        with tempfile.NamedTemporaryFile() as logfile:
            loop = asyncio._wrap_loop()
            proc = ForkProcess(
                scheduler=loop,
                target=self._test_spawn_logfile,
                args=(logfile.name, functools.partial(print, test_string, end="")),
            )
            proc.start()
            self.assertEqual(proc.wait(), os.EX_OK)

            with open(logfile.name, "rb") as output:
                self.assertEqual(output.read(), test_string.encode("utf-8"))

    def test_spawn_logfile_no_send_handle(self):
        with patch(
            "portage.util._async.ForkProcess.ForkProcess._HAVE_SEND_HANDLE", new=False
        ):
            self.test_spawn_logfile()
