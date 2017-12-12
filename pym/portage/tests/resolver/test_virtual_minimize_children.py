# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class VirtualMinimizeChildrenTestCase(TestCase):

	def testVirtualMinimizeChildren(self):
		ebuilds = {
			'app-misc/bar-1': {
				'EAPI': '6',
				'RDEPEND': 'virtual/foo'
			},
			'virtual/foo-1': {
				'EAPI': '6',
				'RDEPEND': '|| ( app-misc/A app-misc/B ) || ( app-misc/B app-misc/C )'
			},
			'app-misc/A-1': {
				'EAPI': '6',
			},
			'app-misc/B-1': {
				'EAPI': '6',
			},
			'app-misc/C-1': {
				'EAPI': '6',
			},
		}

		test_cases = (
			# Test bug 632026, where we want to minimize the number of
			# packages chosen to satisfy overlapping || deps like
			# "|| ( foo bar ) || ( bar baz )".
			ResolverPlaygroundTestCase(
				['app-misc/bar'],
				success=True,
				mergelist=[
					'app-misc/B-1',
					'virtual/foo-1',
					'app-misc/bar-1',
				],
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

		# If app-misc/A and app-misc/C are installed then
		# that choice should be preferred over app-misc/B.
		installed = {
			'app-misc/A-1': {
				'EAPI': '6',
			},
			'app-misc/C-1': {
				'EAPI': '6',
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				['app-misc/bar'],
				success=True,
				mergelist=[
					'virtual/foo-1',
					'app-misc/bar-1',
				],
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def testOverlapSlotConflict(self):
		ebuilds = {
			'app-misc/bar-1': {
				'EAPI': '6',
				'RDEPEND': 'virtual/foo'
			},
			'virtual/foo-1': {
				'EAPI': '6',
				'RDEPEND': '|| ( app-misc/A >=app-misc/B-2 ) || ( <app-misc/B-2 app-misc/C )'
			},
			'app-misc/A-1': {
				'EAPI': '6',
			},
			'app-misc/B-2': {
				'EAPI': '6',
			},
			'app-misc/B-1': {
				'EAPI': '6',
			},
			'app-misc/C-1': {
				'EAPI': '6',
			},
		}

		test_cases = (
			# Here the ( >=app-misc/B-2 <app-misc/B-2 ) choice is not satisfiable.
			ResolverPlaygroundTestCase(
				['app-misc/bar'],
				success=True,
				ambiguous_merge_order=True,
				mergelist=[
					(
						'app-misc/C-1',
						'app-misc/A-1',
					),
					'virtual/foo-1',
					'app-misc/bar-1',
				]
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
