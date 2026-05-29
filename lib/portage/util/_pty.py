# Copyright 2010-2024 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import fcntl
import platform
import pty
import struct
import termios
from typing import Optional

import os
from portage.util import writemsg

# Disable the use of openpty on Solaris as it seems Python's openpty
# implementation doesn't play nice on Solaris with Portage's
# behaviour causing hangs/deadlocks.
# Additional note for the future: on Interix, pipes do NOT work, so
# _disable_openpty on Interix must *never* be True
_disable_openpty = platform.system() in ("SunOS",)

_fbsd_test_pty = platform.system() == "FreeBSD"

_USHRT_MAX = (1 << (struct.calcsize("H") * 8)) - 1


def _get_term_size(given_fd: Optional[int]) -> tuple[int, int]:
    """
    Return non-zero terminal dimensions for a newly allocated pty.

    Python's pty module leaves new ptys at 0x0. Try to determine the
    dimensions from the given descriptor, the standard descriptors and
    COLUMNS/LINES before settling for a conventional default.
    """
    for fd in (given_fd, 0, 1, 2):
        if fd is None:
            continue
        try:
            size = os.get_terminal_size(fd)
        except OSError:
            continue
        if 0 < size.columns <= _USHRT_MAX and 0 < size.lines <= _USHRT_MAX:
            return size.lines, size.columns

    try:
        columns = int(os.environ.get("COLUMNS") or 0)
    except ValueError:
        columns = 0
    if 0 < columns <= _USHRT_MAX:
        try:
            lines = int(os.environ.get("LINES") or 0)
        except ValueError:
            lines = 0
        return (lines if 0 < lines <= _USHRT_MAX else 24), columns

    return 24, 80


def _create_pty_or_pipe(
    copy_term_size: Optional[int] = None,
) -> tuple[int, int]:
    """
    Try to create a pty, falling back to a normal pipe if that fails.

    @param copy_term_size: If this is a tty descriptor, defer to its
            dimensions during pty initialisation.
    @type copy_term_size: int
    @rtype: tuple
    @return: A tuple of (master_fd, slave_fd).
    """

    got_pty = False

    global _disable_openpty, _fbsd_test_pty

    if _fbsd_test_pty and not _disable_openpty:
        # Test for python openpty breakage after freebsd7 to freebsd8
        # upgrade, which results in a 'Function not implemented' error
        # and the process being killed.
        pid = os.fork()
        if pid == 0:
            pty.openpty()
            os._exit(os.EX_OK)
        pid, status = os.waitpid(pid, 0)
        if (status & 0xFF) == 140:
            _disable_openpty = True
        _fbsd_test_pty = False

    if _disable_openpty:
        master_fd, slave_fd = os.pipe()
    else:
        try:
            master_fd, slave_fd = pty.openpty()
            got_pty = True
        except OSError as e:
            _disable_openpty = True
            writemsg(f"openpty failed: '{str(e)}'\n", noiselevel=-1)
            del e
            master_fd, slave_fd = os.pipe()

    if got_pty:
        # Disable post-processing of output since otherwise weird
        # things like \n -> \r\n transformations may occur.
        mode = termios.tcgetattr(slave_fd)
        mode[1] &= ~termios.OPOST
        termios.tcsetattr(slave_fd, termios.TCSANOW, mode)

        # A pty allocated by Python has a default window size of 0x0. Setting
        # the dimensions directly prevents child processes from observing that
        # value, and avoids set_term_size(), which would otherwise spawn
        # stty(1). The ioctl is issued directly because termios.tcsetwinsize()
        # requires at least Python 3.11.
        rows, columns = _get_term_size(copy_term_size)
        fcntl.ioctl(
            slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0)
        )

    return master_fd, slave_fd
