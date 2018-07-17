# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import Atom, use_reduce
from portage.dep.dep_check import _overlap_dnf

class OverlapDNFTestCase(TestCase):

	def testOverlapDNF(self):

		test_cases = (
			(
				'|| ( cat/A cat/B ) cat/E || ( cat/C cat/D )',
				[['||', 'cat/A', 'cat/B'], 'cat/E', ['||', 'cat/C', 'cat/D']],
			),
			(
				'|| ( cat/A cat/B ) cat/D || ( cat/B cat/C )',
				['cat/D', ['||', ['cat/A', 'cat/B'], ['cat/A', 'cat/C'], ['cat/B', 'cat/B'], ['cat/B', 'cat/C']]],
			),
			(
				'|| ( cat/A cat/B ) || ( cat/C cat/D )  || ( ( cat/B cat/E ) cat/F )',
				[['||', ['cat/A', 'cat/B', 'cat/E'], ['cat/A', 'cat/F'], ['cat/B', 'cat/B', 'cat/E'], ['cat/B', 'cat/F']], ['||', 'cat/C', 'cat/D']],
			),
		)

		for dep_str, result in test_cases:
			self.assertEqual(_overlap_dnf(use_reduce(dep_str, token_class=Atom, opconvert=True)), result)
