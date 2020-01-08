# Copyright 2011-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class KeywordsTestCase(TestCase):

	def testStableConfig(self):
		# Only accept stable keywords for a particular ARCH.

		user_config = {
			'package.accept_keywords':
				(
					'*/* -* x86',
				),
		}

		ebuilds = {
			'app-misc/A-1': {'KEYWORDS': 'x86'},
			'app-misc/B-1': {'KEYWORDS': '~x86'},
			'app-misc/C-1': {'KEYWORDS': '*'},
			'app-misc/D-1': {'KEYWORDS': '~*'},
			'app-misc/E-1': {'KEYWORDS': 'arm'},
			'app-misc/F-1': {'KEYWORDS': '~arm'},
			'app-misc/G-1': {'KEYWORDS': ''},
		}

		test_cases = (

			ResolverPlaygroundTestCase(
				['app-misc/A'],
				success = True,
				mergelist = ['app-misc/A-1']),

			ResolverPlaygroundTestCase(
				['app-misc/B'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/B-1',),
				mergelist = ['app-misc/B-1']),

			ResolverPlaygroundTestCase(
				['app-misc/C'],
				success = True,
				mergelist = ['app-misc/C-1']),

			ResolverPlaygroundTestCase(
				['app-misc/D'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/D-1',),
				mergelist = ['app-misc/D-1']),

			ResolverPlaygroundTestCase(
				['app-misc/E'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/E-1',),
				mergelist = ['app-misc/E-1']),

			ResolverPlaygroundTestCase(
				['app-misc/F'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/F-1',),
				mergelist = ['app-misc/F-1']),

			ResolverPlaygroundTestCase(
				['app-misc/G'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/G-1',),
				mergelist = ['app-misc/G-1']),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			user_config=user_config)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testAnyStableConfig(self):
		# Accept stable keywords for any ARCH.

		user_config = {
			'package.accept_keywords':
				(
					'*/* -* *',
				),
		}

		ebuilds = {
			'app-misc/A-1': {'KEYWORDS': 'x86'},
			'app-misc/B-1': {'KEYWORDS': '~x86'},
			'app-misc/C-1': {'KEYWORDS': '*'},
			'app-misc/D-1': {'KEYWORDS': '~*'},
			'app-misc/E-1': {'KEYWORDS': 'arm'},
			'app-misc/F-1': {'KEYWORDS': '~arm'},
			'app-misc/G-1': {'KEYWORDS': ''},
		}

		test_cases = (

			ResolverPlaygroundTestCase(
				['app-misc/A'],
				success = True,
				mergelist = ['app-misc/A-1']),

			ResolverPlaygroundTestCase(
				['app-misc/B'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/B-1',),
				mergelist = ['app-misc/B-1']),

			ResolverPlaygroundTestCase(
				['app-misc/C'],
				success = True,
				mergelist = ['app-misc/C-1']),

			ResolverPlaygroundTestCase(
				['app-misc/D'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/D-1',),
				mergelist = ['app-misc/D-1']),

			ResolverPlaygroundTestCase(
				['app-misc/E'],
				success = True,
				mergelist = ['app-misc/E-1']),

			ResolverPlaygroundTestCase(
				['app-misc/F'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/F-1',),
				mergelist = ['app-misc/F-1']),

			ResolverPlaygroundTestCase(
				['app-misc/G'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/G-1',),
				mergelist = ['app-misc/G-1']),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			user_config=user_config)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testUnstableConfig(self):
		# Accept stable and unstable keywords for a particular ARCH.

		user_config = {
			'package.accept_keywords':
				(
					'*/* -* x86 ~x86',
				),
		}

		ebuilds = {
			'app-misc/A-1': {'KEYWORDS': 'x86'},
			'app-misc/B-1': {'KEYWORDS': '~x86'},
			'app-misc/C-1': {'KEYWORDS': '*'},
			'app-misc/D-1': {'KEYWORDS': '~*'},
			'app-misc/E-1': {'KEYWORDS': 'arm'},
			'app-misc/F-1': {'KEYWORDS': '~arm'},
			'app-misc/G-1': {'KEYWORDS': ''},
		}

		test_cases = (

			ResolverPlaygroundTestCase(
				['app-misc/A'],
				success = True,
				mergelist = ['app-misc/A-1']),

			ResolverPlaygroundTestCase(
				['app-misc/B'],
				success = True,
				mergelist = ['app-misc/B-1']),

			ResolverPlaygroundTestCase(
				['app-misc/C'],
				success = True,
				mergelist = ['app-misc/C-1']),

			ResolverPlaygroundTestCase(
				['app-misc/D'],
				success = True,
				mergelist = ['app-misc/D-1']),

			ResolverPlaygroundTestCase(
				['app-misc/E'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/E-1',),
				mergelist = ['app-misc/E-1']),

			ResolverPlaygroundTestCase(
				['app-misc/F'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/F-1',),
				mergelist = ['app-misc/F-1']),

			ResolverPlaygroundTestCase(
				['app-misc/G'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/G-1',),
				mergelist = ['app-misc/G-1']),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			user_config=user_config)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testAnyUnstableConfig(self):
		# Accept unstable keywords for any ARCH.

		user_config = {
			'package.accept_keywords':
				(
					'*/* -* * ~*',
				),
		}

		ebuilds = {
			'app-misc/A-1': {'KEYWORDS': 'x86'},
			'app-misc/B-1': {'KEYWORDS': '~x86'},
			'app-misc/C-1': {'KEYWORDS': '*'},
			'app-misc/D-1': {'KEYWORDS': '~*'},
			'app-misc/E-1': {'KEYWORDS': 'arm'},
			'app-misc/F-1': {'KEYWORDS': '~arm'},
			'app-misc/G-1': {'KEYWORDS': ''},
		}

		test_cases = (

			ResolverPlaygroundTestCase(
				['app-misc/A'],
				success = True,
				mergelist = ['app-misc/A-1']),

			ResolverPlaygroundTestCase(
				['app-misc/B'],
				success = True,
				mergelist = ['app-misc/B-1']),

			ResolverPlaygroundTestCase(
				['app-misc/C'],
				success = True,
				mergelist = ['app-misc/C-1']),

			ResolverPlaygroundTestCase(
				['app-misc/D'],
				success = True,
				mergelist = ['app-misc/D-1']),

			ResolverPlaygroundTestCase(
				['app-misc/E'],
				success = True,
				mergelist = ['app-misc/E-1']),

			ResolverPlaygroundTestCase(
				['app-misc/F'],
				success = True,
				mergelist = ['app-misc/F-1']),

			ResolverPlaygroundTestCase(
				['app-misc/G'],
				success = False,
				options={'--autounmask': True},
				unstable_keywords = ('app-misc/G-1',),
				mergelist = ['app-misc/G-1']),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			user_config=user_config)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testIgnoreKeywordsConfig(self):
		# Ignore keywords entirely (accept **)

		user_config = {
			'package.accept_keywords':
				(
					'*/* -* **',
				),
		}

		ebuilds = {
			'app-misc/A-1': {'KEYWORDS': 'x86'},
			'app-misc/B-1': {'KEYWORDS': '~x86'},
			'app-misc/C-1': {'KEYWORDS': '*'},
			'app-misc/D-1': {'KEYWORDS': '~*'},
			'app-misc/E-1': {'KEYWORDS': 'arm'},
			'app-misc/F-1': {'KEYWORDS': '~arm'},
			'app-misc/G-1': {'KEYWORDS': ''},
		}

		test_cases = (

			ResolverPlaygroundTestCase(
				['app-misc/A'],
				success = True,
				mergelist = ['app-misc/A-1']),

			ResolverPlaygroundTestCase(
				['app-misc/B'],
				success = True,
				mergelist = ['app-misc/B-1']),

			ResolverPlaygroundTestCase(
				['app-misc/C'],
				success = True,
				mergelist = ['app-misc/C-1']),

			ResolverPlaygroundTestCase(
				['app-misc/D'],
				success = True,
				mergelist = ['app-misc/D-1']),

			ResolverPlaygroundTestCase(
				['app-misc/E'],
				success = True,
				mergelist = ['app-misc/E-1']),

			ResolverPlaygroundTestCase(
				['app-misc/F'],
				success = True,
				mergelist = ['app-misc/F-1']),

			ResolverPlaygroundTestCase(
				['app-misc/G'],
				success = True,
				mergelist = ['app-misc/G-1']),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			user_config=user_config)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
