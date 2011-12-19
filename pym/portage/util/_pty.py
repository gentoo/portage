# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import fcntl
import platform
import pty
import select
import sys
import termios

from portage import os, _unicode_decode, _unicode_encode
from portage.output import get_term_size, set_term_size
from portage.process import spawn_bash
from portage.util import writemsg

def _can_test_pty_eof():
	"""
	The _test_pty_eof() function seems to hang on most
	kernels other than Linux.
	This was reported for the following kernels which used to work fine
	without this EOF test: Darwin, AIX, FreeBSD.  They seem to hang on
	the slave_file.close() call.  Note that Python's implementation of
	openpty on Solaris already caused random hangs without this EOF test
	and hence is globally disabled.
	@rtype: bool
	@returns: True if _test_pty_eof() won't hang, False otherwise.
	"""
	return platform.system() in ("Linux",)

def _test_pty_eof():
	"""
	Returns True if EOF appears to be handled correctly with pty
	devices. Raises an EnvironmentError from openpty() if it fails.

	This used to be used to detect if the following issue was fixed
	in the currently running version of python:

		http://bugs.python.org/issue5380

	However, array.fromfile() use has since been abandoned due to
	bugs that exist in all known versions of Python (including Python
	2.7 and Python 3.2). See PipeReaderArrayTestCase, for example.
	This is somewhat unfortunate, since the combination of 
	array.fromfile() and array.tofile() is approximately 10% faster
	than the combination of os.read() and os.write().
	"""

	use_fork = False

	test_string = 2 * "blah blah blah\n"
	test_string = _unicode_decode(test_string,
		encoding='utf_8', errors='strict')

	# may raise EnvironmentError
	master_fd, slave_fd = pty.openpty()

	# Non-blocking mode is required for Darwin kernel.
	fcntl.fcntl(master_fd, fcntl.F_SETFL,
		fcntl.fcntl(master_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

	# Disable post-processing of output since otherwise weird
	# things like \n -> \r\n transformations may occur.
	mode = termios.tcgetattr(slave_fd)
	mode[1] &= ~termios.OPOST
	termios.tcsetattr(slave_fd, termios.TCSANOW, mode)

	# Simulate a subprocess writing some data to the
	# slave end of the pipe, and then exiting.
	pid = None
	if use_fork:
		pids = spawn_bash(_unicode_encode("echo -n '%s'" % test_string,
			encoding='utf_8', errors='strict'), env=os.environ,
			fd_pipes={0:sys.stdin.fileno(), 1:slave_fd, 2:slave_fd},
			returnpid=True)
		if isinstance(pids, int):
			os.close(master_fd)
			os.close(slave_fd)
			raise EnvironmentError('spawn failed')
		pid = pids[0]
	else:
		os.write(slave_fd, _unicode_encode(test_string,
			encoding='utf_8', errors='strict'))
	os.close(slave_fd)

	# If using a fork, we must wait for the child here,
	# in order to avoid a race condition that would
	# lead to inconsistent results.
	if pid is not None:
		os.waitpid(pid, 0)

	data = []
	iwtd = [master_fd]
	owtd = []
	ewtd = []

	while True:

		events = select.select(iwtd, owtd, ewtd)
		if not events[0]:
			# EOF
			break

		buf = None
		try:
			buf = os.read(master_fd, 1024)
		except OSError as e:
			# EIO happens with pty on Linux after the
			# slave end of the pty has been closed.
			if e.errno == errno.EIO:
				# EOF: return empty string of bytes
				buf = b''
			elif e.errno == errno.EAGAIN:
				# EAGAIN: return None
				buf = None
			else:
				raise

		if buf is None:
			pass
		elif not buf:
			# EOF
			break
		else:
			data.append(buf)

	os.close(master_fd)

	return test_string == _unicode_decode(b''.join(data), encoding='utf_8', errors='strict')

# If _test_pty_eof() can't be used for runtime detection of
# http://bugs.python.org/issue5380, openpty can't safely be used
# unless we can guarantee that the current version of python has
# been fixed (affects all current versions of python3). When
# this issue is fixed in python3, we can add another sys.hexversion
# conditional to enable openpty support in the fixed versions.
if sys.hexversion >= 0x3000000 and not _can_test_pty_eof():
	_disable_openpty = True
else:
	# Disable the use of openpty on Solaris as it seems Python's openpty
	# implementation doesn't play nice on Solaris with Portage's
	# behaviour causing hangs/deadlocks.
	# Similarly, on FreeMiNT, reading just always fails, causing Portage
	# to think the system is malfunctioning, and returning that as error
	# message.
	# Additional note for the future: on Interix, pipes do NOT work, so
	# _disable_openpty on Interix must *never* be True
	_disable_openpty = platform.system() in ("SunOS", "FreeMiNT",)
_tested_pty = False

if not _can_test_pty_eof():
	# Skip _test_pty_eof() on systems where it hangs.
	_tested_pty = True

_fbsd_test_pty = platform.system() == 'FreeBSD'

def _create_pty_or_pipe(copy_term_size=None):
	"""
	Try to create a pty and if then fails then create a normal
	pipe instead.

	@param copy_term_size: If a tty file descriptor is given
		then the term size will be copied to the pty.
	@type copy_term_size: int
	@rtype: tuple
	@returns: A tuple of (is_pty, master_fd, slave_fd) where
		is_pty is True if a pty was successfully allocated, and
		False if a normal pipe was allocated.
	"""

	got_pty = False

	global _disable_openpty, _fbsd_test_pty, _tested_pty
	if not (_tested_pty or _disable_openpty):
		try:
			if not _test_pty_eof():
				_disable_openpty = True
		except EnvironmentError as e:
			_disable_openpty = True
			writemsg("openpty failed: '%s'\n" % str(e),
				noiselevel=-1)
			del e
		_tested_pty = True

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
