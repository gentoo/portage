# Copyright 2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.exception import InvalidDependString
from portage.dep import paren_reduce, use_reduce
import portage.dep
portage.dep._dep_check_strict = True

class UseReduce(TestCase):

	def testUseReduce(self):

		tests = (
			('|| ( x y )',                                           True  ),
			('|| x',                                                 False ),
			('foo? ( x y )',                                         True  ),
			('foo? ( bar? x y )',                                    False ),
			('foo? x',                                               False ),
		)

		for dep_str, valid in tests:
			try:
				use_reduce(paren_reduce(dep_str), matchall=True)
			except InvalidDependString:
				self.assertEqual(valid, False)
			else:
				self.assertEqual(valid, True)
