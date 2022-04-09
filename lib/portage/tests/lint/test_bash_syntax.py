# Copyright 2010-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import chain
import stat
import subprocess

from portage.const import BASH_BINARY, PORTAGE_BASE_PATH, PORTAGE_BIN_PATH
from portage.tests import TestCase
from portage import os_unicode_fs, _encodings


class BashSyntaxTestCase(TestCase):
    def testBashSyntax(self):
        locations = [PORTAGE_BIN_PATH]
        misc_dir = os_unicode_fs.path.join(PORTAGE_BASE_PATH, "misc")
        if os_unicode_fs.path.isdir(misc_dir):
            locations.append(misc_dir)
        for parent, dirs, files in chain.from_iterable(
            os_unicode_fs.walk(x) for x in locations
        ):
            parent = parent.decode(encoding=_encodings["fs"], errors="strict")
            for x in files:
                x = x.decode(encoding=_encodings["fs"], errors="strict")
                ext = x.split(".")[-1]
                if ext in (".py", ".pyc", ".pyo"):
                    continue
                x = os_unicode_fs.path.join(parent, x)
                st = os_unicode_fs.lstat(x)
                if not stat.S_ISREG(st.st_mode):
                    continue

                # Check for bash shebang
                f = open(x.encode(encoding=_encodings["fs"], errors="strict"), "rb")
                line = f.readline().decode(
                    encoding=_encodings["content"], errors="replace"
                )
                f.close()
                if line[:2] == "#!" and "bash" in line:
                    cmd = [BASH_BINARY, "-n", x]
                    cmd = [
                        x.encode(encoding=_encodings["fs"], errors="strict")
                        for x in cmd
                    ]
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                    )
                    output = proc.communicate()[0].decode(encoding=_encodings["fs"])
                    status = proc.wait()
                    self.assertEqual(
                        os_unicode_fs.WIFEXITED(status)
                        and os_unicode_fs.WEXITSTATUS(status) == os_unicode_fs.EX_OK,
                        True,
                        msg=output,
                    )
