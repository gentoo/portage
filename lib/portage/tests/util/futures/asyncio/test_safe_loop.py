# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import asyncio as _real_asyncio
import gc

from portage.tests import TestCase
from portage.util.futures import asyncio


class SafeLoopTestCase(TestCase):
    def test_main_loop_after_asyncio_run(self):
        """
        _safe_loop() must return the main loop again once an asyncio.run
        loop that displaced its entry is gone.
        """
        mainloop = asyncio._safe_loop()

        async def get_loop():
            return asyncio._safe_loop()

        self.assertIsNot(_real_asyncio.run(get_loop()), mainloop)
        gc.collect()

        self.assertIs(asyncio._safe_loop(), mainloop)
        self.assertFalse(mainloop.is_closed())
