# Copyright 2009-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util._pty import _can_test_pty_eof, _test_pty_eof

class PtyEofTestCase(TestCase):

	def testPtyEofFdopenBuffered(self):
		# This tests if the following python issue is fixed yet:
		#   http://bugs.python.org/issue5380
		# Since it might not be fixed, mark as todo.
		self.todo = True
		# The result is only valid if openpty does not raise EnvironmentError.
		if _can_test_pty_eof():
			try:
				self.assertEqual(_test_pty_eof(fdopen_buffered=True), True)
			except EnvironmentError:
				pass

	def testPtyEofFdopenUnBuffered(self):
		# New development: It appears that array.fromfile() is usable
		# with python3 as long as fdopen is called with a bufsize
		# argument of 0.

		# The result is only valid if openpty does not raise EnvironmentError.
		if _can_test_pty_eof():
			try:
				self.assertEqual(_test_pty_eof(), True)
			except EnvironmentError:
				pass
