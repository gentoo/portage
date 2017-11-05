# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import use_reduce
from portage.dep._dnf import dnf_convert

class DNFConvertTestCase(TestCase):

	def testDNFConvert(self):

		test_cases = (
			(
				'|| ( A B ) || ( C D )',
				[['||', ['A', 'C'], ['A', 'D'], ['B', 'C'], ['B', 'D']]],
			),
			(
				'|| ( A B ) || ( B C )',
				[['||', ['A', 'B'], ['A', 'C'], ['B', 'B'], ['B', 'C']]],
			),
			(
				'|| ( A ( B C D ) )',
				[['||', 'A', ['B', 'C', 'D']]],
			),
			(
				'|| ( A ( B C D ) ) E',
				[['||', ['E', 'A'], ['E', 'B', 'C', 'D']]],
			),
			(
				'|| ( A ( B C ) ) || ( D E ) F',
				[['||', ['F', 'A', 'D'], ['F', 'A', 'E'], ['F', 'B', 'C', 'D'], ['F', 'B', 'C', 'E']]],
			),
			(
				'|| ( A ( B C || ( D E ) ) ( F G ) H )',
				[['||', 'A', ['B', 'C', 'D'], ['B', 'C', 'E'], ['F', 'G'], 'H']],
			),
			(
				'|| ( A ( B C || ( D E ) ) F )',
				[['||', 'A', ['B', 'C', 'D'], ['B', 'C', 'E'], 'F']],
			),
			(
				'|| ( A ( C || ( D E ) || ( F G ) ) H )',
				[['||', 'A', ['C', 'D', 'F'], ['C', 'D', 'G'], ['C', 'E', 'F'], ['C', 'E', 'G'], 'H']],
			),
		)

		for dep_str, result in test_cases:
			self.assertEqual(dnf_convert(use_reduce(dep_str, opconvert=True)), result)
