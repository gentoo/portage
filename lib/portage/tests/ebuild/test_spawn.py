# Copyright 1998-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import tempfile
import os
import portage

from portage.const import BASH_BINARY
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from _emerge.SpawnProcess import SpawnProcess


class SpawnTestCase(TestCase):
    def testLogfile(self):
        logfile = None
        try:
            fd, logfile = tempfile.mkstemp()
            os.close(fd)
            null_fd = os.open("/dev/null", os.O_RDWR)
            test_string = 2 * "blah blah blah\n"
            proc = SpawnProcess(
                args=[BASH_BINARY, "-c", f"echo -n '{test_string}'"],
                env={},
                fd_pipes={0: portage._get_stdin().fileno(), 1: null_fd, 2: null_fd},
                scheduler=global_event_loop(),
                logfile=logfile,
            )
            proc.start()
            os.close(null_fd)
            self.assertEqual(proc.wait(), os.EX_OK)
            f = open(
                logfile.encode("utf-8", "strict"),
                encoding="utf-8",
                errors="strict",
            )
            log_content = f.read()
            f.close()
            # When logging passes through a pty, this comparison will fail
            # unless the oflag terminal attributes have the termios.OPOST
            # bit disabled. Otherwise, transformations such as \n -> \r\n
            # may occur.
            self.assertEqual(test_string, log_content)
        finally:
            if logfile:
                try:
                    os.unlink(logfile)
                except OSError as e:
                    if e.errno != errno.ENOENT:
                        raise
                    del e
