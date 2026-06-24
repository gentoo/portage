# Copyright 2010-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import chain
import stat
import subprocess

import os
from portage.const import BASH_BINARY, PORTAGE_BASE_PATH, PORTAGE_BIN_PATH
from portage.tests import TestCase


class BashSyntaxTestCase(TestCase):
    def testBashSyntax(self):
        locations = [PORTAGE_BIN_PATH]
        misc_dir = os.path.join(PORTAGE_BASE_PATH, "misc")
        if os.path.isdir(misc_dir):
            locations.append(misc_dir)
        for parent, dirs, files in chain.from_iterable(os.walk(x) for x in locations):
            if isinstance(parent, bytes):
                parent = parent.decode("utf-8", "strict")
            for x in files:
                if isinstance(x, bytes):
                    x = x.decode("utf-8", "strict")
                ext = x.split(".")[-1]
                if ext in (".py", ".pyc", ".pyo"):
                    continue
                x = os.path.join(parent, x)
                st = os.lstat(x)
                if not stat.S_ISREG(st.st_mode):
                    continue

                # Check for bash shebang
                f = open(x, "rb")
                line = f.readline().decode("utf-8", "replace")
                f.close()
                if line[:2] == "#!" and "bash" in line:
                    cmd = [BASH_BINARY, "-n", x]
                    cmd = [x for x in cmd]
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                    )
                    output = proc.communicate()[0].decode("utf-8", "replace")
                    status = proc.wait()
                    self.assertEqual(
                        os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK,
                        True,
                        msg=output,
                    )
