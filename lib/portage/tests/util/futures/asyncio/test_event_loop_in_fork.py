# Copyright 2018-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from portage.tests import TestCase
from portage.util._async.AsyncFunction import AsyncFunction
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.futures import asyncio


def fork_main():
    loop = asyncio._wrap_loop()
    # Before python 3.12 this fails with python's default event loop policy,
    # see https://bugs.python.org/issue22087.
    loop.run_until_complete(asyncio.sleep(0.1, loop=loop))
    loop.close()


def async_main(fork_exitcode, loop=None):
    loop = asyncio._wrap_loop(loop)
    proc = AsyncFunction(scheduler=loop, target=fork_main)
    proc.start()
    proc.async_wait().add_done_callback(
        lambda future: fork_exitcode.set_result(future.result())
    )


class EventLoopInForkTestCase(TestCase):
    """
    Before python 3.12 the default asyncio event loop policy does not support loops
    running in forks, see https://bugs.python.org/issue22087.
    """

    def testEventLoopInForkTestCase(self):
        loop = global_event_loop()
        fork_exitcode = loop.create_future()
        # Make async_main fork while the loop is running, which would
        # trigger https://bugs.python.org/issue22087 with asyncio's
        # default event loop policy before python 3.12.
        loop.call_soon(async_main, fork_exitcode)
        assert loop.run_until_complete(fork_exitcode) == os.EX_OK
