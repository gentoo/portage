# Copyright 1998-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import pty

import portage
from portage import os
from portage.tests import TestCase

class PtyEofTestCase(TestCase):

	def testPtyEof(self):
		# This tests if the following python issue is fixed yet:
		#   http://bugs.python.org/issue5380
		# Since it might not be fixed, mark as todo.
		self.todo = True
		result = portage._test_pty_eof()
		# The result is only valid if openpty works (result is
		# True or False, not None).
		if result is not None:
			self.assertEqual(result, True)
