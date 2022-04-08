# Copyright 1998-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import io
import tempfile
import portage
from portage import os_unicode_fs, _encodings, _unicode_encode
from portage.const import BASH_BINARY
from portage.tests import TestCase
from portage.util._eventloop.global_event_loop import global_event_loop
from _emerge.SpawnProcess import SpawnProcess


class SpawnTestCase(TestCase):
    def testLogfile(self):
        logfile = None
        try:
            fd, logfile = tempfile.mkstemp()
            os_unicode_fs.close(fd)
            null_fd = os_unicode_fs.open("/dev/null", os_unicode_fs.O_RDWR)
            test_string = 2 * "blah blah blah\n"
            proc = SpawnProcess(
                args=[BASH_BINARY, "-c", "echo -n '%s'" % test_string],
                env={},
                fd_pipes={0: portage._get_stdin().fileno(), 1: null_fd, 2: null_fd},
                scheduler=global_event_loop(),
                logfile=logfile,
            )
            proc.start()
            os_unicode_fs.close(null_fd)
            self.assertEqual(proc.wait(), os_unicode_fs.EX_OK)
            f = io.open(
                _unicode_encode(logfile, encoding=_encodings["fs"], errors="strict"),
                mode="r",
                encoding=_encodings["content"],
                errors="strict",
            )
            log_content = f.read()
            f.close()
            # When logging passes through a pty, this comparison will fail
            # unless the oflag terminal attributes have the termios.OPOST
            # bit disabled. Otherwise, tranformations such as \n -> \r\n
            # may occur.
            self.assertEqual(test_string, log_content)
        finally:
            if logfile:
                try:
                    os_unicode_fs.unlink(logfile)
                except EnvironmentError as e:
                    if e.errno != errno.ENOENT:
                        raise
                    del e
