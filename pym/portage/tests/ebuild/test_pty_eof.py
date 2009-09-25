# Copyright 2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage
from portage.tests import TestCase

class PtyEofTestCase(TestCase):

	def testPtyEof(self):
		# This tests if the following python issue is fixed yet:
		#   http://bugs.python.org/issue5380
		# Since it might not be fixed, mark as todo.
		self.todo = True
		# The result is only valid if openpty does not raise EnvironmentError.
		try:
			self.assertEqual(portage._test_pty_eof(), True)
		except EnvironmentError:
			pass
