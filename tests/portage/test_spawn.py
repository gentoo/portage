# Copyright 1998-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import errno, os, sys
from unittest import TestCase

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
			spawn("echo -n '%s'" % test_string, settings, logfile=logfile,
				fd_pipes={0:sys.stdin.fileno(), 1:null_fd, 2:null_fd})
			os.close(null_fd)
			f = open(logfile, 'r')
			log_content = f.read()
			f.close()
			# When logging passes through a pty, it's lines will be separated
			# by '\r\n', so use splitlines before comparing results.
			self.assertEqual(test_string.splitlines(),
				log_content.splitlines())
		finally:
			if logfile:
				try:
					os.unlink(logfile)
				except EnvironmentError, e:
					if e.errno != errno.ENOENT:
						raise
					del e
