# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import platform
import pty
import termios

from portage import os
from portage.output import get_term_size, set_term_size
from portage.util import writemsg

# Disable the use of openpty on Solaris as it seems Python's openpty
# implementation doesn't play nice on Solaris with Portage's
# behaviour causing hangs/deadlocks.
# Additional note for the future: on Interix, pipes do NOT work, so
# _disable_openpty on Interix must *never* be True
_disable_openpty = platform.system() in ("SunOS",)

_fbsd_test_pty = platform.system() == 'FreeBSD'

def _create_pty_or_pipe(copy_term_size=None):
	"""
	Try to create a pty and if then fails then create a normal
	pipe instead.

	@param copy_term_size: If a tty file descriptor is given
		then the term size will be copied to the pty.
	@type copy_term_size: int
	@rtype: tuple
	@return: A tuple of (is_pty, master_fd, slave_fd) where
		is_pty is True if a pty was successfully allocated, and
		False if a normal pipe was allocated.
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
		if (status & 0xff) == 140:
			_disable_openpty = True
		_fbsd_test_pty = False

	if _disable_openpty:
		master_fd, slave_fd = os.pipe()
	else:
		try:
			master_fd, slave_fd = pty.openpty()
			got_pty = True
		except EnvironmentError as e:
			_disable_openpty = True
			writemsg("openpty failed: '%s'\n" % str(e),
				noiselevel=-1)
			del e
			master_fd, slave_fd = os.pipe()

	if got_pty:
		# Disable post-processing of output since otherwise weird
		# things like \n -> \r\n transformations may occur.
		mode = termios.tcgetattr(slave_fd)
		mode[1] &= ~termios.OPOST
		termios.tcsetattr(slave_fd, termios.TCSANOW, mode)

	if got_pty and \
		copy_term_size is not None and \
		os.isatty(copy_term_size):
		rows, columns = get_term_size()
		set_term_size(rows, columns, slave_fd)

	return (got_pty, master_fd, slave_fd)
