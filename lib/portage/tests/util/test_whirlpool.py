# Copyright 2011-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import subprocess

import portage
from portage import os_unicode_fs
from portage.const import PORTAGE_PYM_PATH
from portage.tests import TestCase


class WhirlpoolTestCase(TestCase):
    def testBundledWhirlpool(self):
        # execute the tests bundled with the whirlpool module
        retval = subprocess.call(
            [
                portage._python_interpreter,
                "-b",
                "-Wd",
                os_unicode_fs.path.join(PORTAGE_PYM_PATH, "portage/util/whirlpool.py"),
            ]
        )
        self.assertEqual(retval, os_unicode_fs.EX_OK)
