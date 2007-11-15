# Copyright 1998-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import errno, os, sys
from portage.tests import TestCase

class SpawnTestCase(TestCase):

	def testLogfile(self):
		from portage import settings, spawn
		from tempfile import mkstemp
		logfile = None
		try:
			fd, logfile = mkstemp()
			os.close(fd)
			null_fd = os.open('/dev/null', os.O_RDWR)
			test_string = 2 * "blah blah blah\n"
			# Test cases are unique because they run inside src_test() which
			# may or may not already be running within a sandbox. Interaction
			# with SANDBOX_* variables may trigger unwanted sandbox violations
			# that are only reproducible with certain combinations of sandbox,
			# usersandbox, and userpriv FEATURES. Attempts to filter SANDBOX_*
			# variables can interfere with a currently running sandbox
			# instance. Therefore, use free=1 here to avoid potential
			# interactions (see bug #190268).
			spawn("echo -n '%s'" % test_string, settings, logfile=logfile,
				free=1, fd_pipes={0:sys.stdin.fileno(), 1:null_fd, 2:null_fd})
			os.close(null_fd)
			f = open(logfile, 'r')
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
					os.unlink(logfile)
				except EnvironmentError, e:
					if e.errno != errno.ENOENT:
						raise
					del e
