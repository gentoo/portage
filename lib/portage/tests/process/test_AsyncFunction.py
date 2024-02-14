# Copyright 2020-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys

import portage
from portage import multiprocessing, os
from portage.tests import TestCase
from portage.util._async.AsyncFunction import AsyncFunction
from portage.util.futures import asyncio
from portage.util.futures._asyncio.streams import _writer
from portage.util.futures.unix_events import _set_nonblocking


class AsyncFunctionTestCase(TestCase):
    @staticmethod
    def _read_from_stdin(pw):
        if pw is not None:
            os.close(pw)
        return "".join(sys.stdin)

    async def _testAsyncFunctionStdin(self, loop):
        test_string = "1\n2\n3\n"
        pr, pw = multiprocessing.Pipe(duplex=False)
        stdin_backup = os.dup(portage._get_stdin().fileno())
        os.dup2(pr.fileno(), portage._get_stdin().fileno())
        pr.close()
        try:
            reader = AsyncFunction(
                # Should automatically inherit stdin as fd_pipes[0]
                # when background is False, for things like
                # emerge --sync --ask (bug 916116).
                background=False,
                scheduler=loop,
                target=self._read_from_stdin,
                args=(
                    (
                        pw.fileno()
                        if multiprocessing.get_start_method() == "fork"
                        else None
                    ),
                ),
            )
            reader.start()
        finally:
            os.dup2(stdin_backup, portage._get_stdin().fileno())
            os.close(stdin_backup)

        _set_nonblocking(pw.fileno())
        with open(pw.fileno(), mode="wb", buffering=0, closefd=False) as pipe_write:
            await _writer(pipe_write, test_string.encode("utf_8"))
        pw.close()
        self.assertEqual((await reader.async_wait()), os.EX_OK)
        self.assertEqual(reader.result, test_string)

    def testAsyncFunctionStdin(self):
        loop = asyncio._wrap_loop()
        loop.run_until_complete(self._testAsyncFunctionStdin(loop=loop))

    def testAsyncFunctionStdinSpawn(self):
        orig_start_method = multiprocessing.get_start_method()
        if orig_start_method == "spawn":
            self.skipTest("multiprocessing start method is already spawn")
        # NOTE: An attempt was made to use multiprocessing.get_context("spawn")
        # here, but it caused the python process to terminate unexpectedly
        # during a send_handle call.
        multiprocessing.set_start_method("spawn", force=True)
        try:
            self.testAsyncFunctionStdin()
        finally:
            multiprocessing.set_start_method(orig_start_method, force=True)

    @staticmethod
    def _test_getpid_fork(preexec_fn=None):
        """
        Verify that portage.getpid() cache is updated in a forked child process.
        """
        if preexec_fn is not None:
            preexec_fn()
        loop = asyncio._wrap_loop()
        proc = AsyncFunction(scheduler=loop, target=portage.getpid)
        proc.start()
        proc.wait()
        return proc.pid == proc.result

    def test_getpid_fork(self):
        self.assertTrue(self._test_getpid_fork())

    @staticmethod
    def _set_start_method_spawn():
        multiprocessing.set_start_method("spawn", force=True)

    def test_spawn_getpid(self):
        """
        Test portage.getpid() with multiprocessing spawn start method.
        """
        loop = asyncio._wrap_loop()
        proc = AsyncFunction(
            scheduler=loop,
            target=self._test_getpid_fork,
            # Don't use partial(multiprocessing.set_start_method)
            # since the set_start_method attribute from the parent
            # process may not be valid in the child process.
            kwargs=dict(preexec_fn=self._set_start_method_spawn),
        )
        proc.start()
        self.assertEqual(proc.wait(), 0)
        self.assertTrue(proc.result)

    def test_getpid_double_fork(self):
        """
        Verify that portage.getpid() cache is updated correctly after
        two forks.
        """
        loop = asyncio._wrap_loop()
        proc = AsyncFunction(scheduler=loop, target=self._test_getpid_fork)
        proc.start()
        self.assertEqual(proc.wait(), 0)
        self.assertTrue(proc.result)
