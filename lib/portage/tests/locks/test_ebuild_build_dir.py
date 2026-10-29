# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os
import subprocess
import sys
import tempfile

from _emerge.EbuildBuildDir import EbuildBuildDir
from portage.const import PORTAGE_PYM_PATH
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop

# Exit 0 if the lock can be taken without waiting, 1 if it is held.
_TRY_LOCK = """
import os, sys
from portage.exception import TryAgain
from portage.locks import lockfile
try:
    lockfile(sys.argv[1], wantnewlockfile=True, flags=os.O_NONBLOCK)
except TryAgain:
    sys.exit(1)
"""


class EbuildBuildDirTestCase(TestCase):
    """
    EbuildBuildDir holds the catdir lock only while it creates the build
    directory, not until the event loop runs again.
    """

    def _catdir_free(self, catdir):
        env = dict(os.environ, PYTHONPATH=PORTAGE_PYM_PATH)
        return subprocess.call([sys.executable, "-c", _TRY_LOCK, catdir], env=env) == 0

    def test_catdir_released(self):
        loop = global_event_loop()
        with tempfile.TemporaryDirectory() as tmpdir:
            catdir = os.path.join(tmpdir, "portage", "dev-libs")
            settings = {"PORTAGE_BUILDDIR": os.path.join(catdir, "A-1")}
            build_dir = EbuildBuildDir(scheduler=loop, settings=settings)

            future = build_dir.async_lock()
            self.assertTrue(self._catdir_free(catdir))
            loop.run_until_complete(future)
            self.assertTrue(build_dir.locked)

            future = build_dir.async_unlock()
            loop.run_until_complete(future)
            self.assertFalse(build_dir.locked)
            self.assertFalse(os.path.exists(catdir))
