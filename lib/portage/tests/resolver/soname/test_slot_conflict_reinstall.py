# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground, ResolverPlaygroundTestCase)

class SonameSlotConflictReinstallTestCase(TestCase):

	def testSonameSlotConflictReinstall(self):

		binpkgs = {

			"app-misc/A-1" : {
				"PROVIDES": "x86_32: libA-1.so",
			},

			"app-misc/A-2" : {
				"PROVIDES": "x86_32: libA-2.so",
			},

			"app-misc/B-0" : {
				"DEPEND": "app-misc/A",
				"RDEPEND": "app-misc/A",
				"REQUIRES": "x86_32: libA-2.so",
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"DEPEND": "<app-misc/A-2",
				"RDEPEND": "<app-misc/A-2"
			},

			"app-misc/D-1" : {
				"PROVIDES": "x86_32: libD-1.so",
			},

			"app-misc/D-2" : {
				"PROVIDES": "x86_32: libD-2.so",
			},

			"app-misc/E-0" : {
				"DEPEND": "app-misc/D",
				"RDEPEND": "app-misc/D",
				"REQUIRES": "x86_32: libD-2.so",
			},

		}

		installed = {

			"app-misc/A-1" : {
				"PROVIDES": "x86_32: libA-1.so",
			},

			"app-misc/B-0" : {
				"DEPEND": "app-misc/A",
				"RDEPEND": "app-misc/A",
				"REQUIRES": "x86_32: libA-1.so",
			},

			"app-misc/C-0" : {
				"DEPEND": "<app-misc/A-2",
				"RDEPEND": "<app-misc/A-2"
			},

			"app-misc/D-1" : {
				"PROVIDES": "x86_32: libD-1.so",
			},

			"app-misc/E-0" : {
				"DEPEND": "app-misc/D",
				"RDEPEND": "app-misc/D",
				"REQUIRES": "x86_32: libD-1.so",
			},

		}

		world = ["app-misc/B", "app-misc/C", "app-misc/E"]

		test_cases = (

			# Test bug #439688, where a slot conflict prevents an
			# upgrade and we don't want to trigger unnecessary rebuilds.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True,
					"--backtrack": 10,
				},
				success = True,
				mergelist = [
					"[binary]app-misc/D-2",
					"[binary]app-misc/E-0"
				]
			),

		)

		playground = ResolverPlayground(binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def testSonameSlotConflictMassRebuild(self):
		"""
		Bug 486580
		Before this bug was fixed, emerge would backtrack for each
		package that needs a rebuild. This could cause it to hit the
		backtrack limit and not rebuild all needed packages.
		"""
		binpkgs = {

			"app-misc/A-1" : {
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/B",
				"REQUIRES": "x86_32: libB-2.so",
			},

			"app-misc/B-1" : {
				"SLOT": "1",
				"PROVIDES": "x86_32: libB-1.so",
			},

			"app-misc/B-2" : {
				"SLOT": "2",
				"PROVIDES": "x86_32: libB-2.so",
			},
		}

		installed = {
			"app-misc/B-1" : {
				"SLOT": "1",
				"PROVIDES": "x86_32: libB-1.so",
			},
		}

		expected_mergelist = [
			'[binary]app-misc/A-1',
			'[binary]app-misc/B-2'
		]

		for i in range(5):
			binpkgs["app-misc/C%sC-1" % i] = {
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/B",
				"REQUIRES": "x86_32: libB-2.so",
			}

			installed["app-misc/C%sC-1" % i] = {
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/B",
				"REQUIRES": "x86_32: libB-1.so",
			}
			for x in ("DEPEND", "RDEPEND"):
				binpkgs["app-misc/A-1"][x] += " app-misc/C%sC" % i

			expected_mergelist.append("[binary]app-misc/C%sC-1" % i)


		test_cases = (
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				ignore_mergelist_order=True,
				all_permutations=True,
				options = {
					"--backtrack": 3,
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True,
				},
				success = True,
				mergelist = expected_mergelist),
		)

		world = []

		playground = ResolverPlayground(binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def testSonameSlotConflictForgottenChild(self):
		"""
		Similar to testSonameSlotConflictMassRebuild above, but this
		time the rebuilds are scheduled, but the package causing the
		rebuild (the child) is not installed.
		"""
		binpkgs = {

			"app-misc/A-2" : {
				"DEPEND": "app-misc/B app-misc/C",
				"RDEPEND": "app-misc/B app-misc/C",
				"REQUIRES": "x86_32: libB-2.so",
			},

			"app-misc/B-2" : {
				"PROVIDES": "x86_32: libB-2.so",
				"SLOT": "2",
			},

			"app-misc/C-1": {
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/B",
				"REQUIRES": "x86_32: libB-2.so",
			},
		}

		installed = {
			"app-misc/A-1" : {
				"DEPEND": "app-misc/B app-misc/C",
				"RDEPEND": "app-misc/B app-misc/C",
				"REQUIRES": "x86_32: libB-1.so",
			},

			"app-misc/B-1" : {
				"PROVIDES": "x86_32: libB-1.so",
				"SLOT": "1",
			},

			"app-misc/C-1": {
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/B",
				"REQUIRES": "x86_32: libB-1.so",
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				options = {
					"--ignore-soname-deps": "n",
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					'[binary]app-misc/B-2',
					'[binary]app-misc/A-2',
				]
			),
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--ignore-soname-deps": "n",
					"--usepkgonly": True,
					"--update": True,
					"--deep": True,
				},
				success = True,
				mergelist = [
					'[binary]app-misc/B-2',
					'[binary]app-misc/C-1',
					'[binary]app-misc/A-2',
				]
			),
		)

		world = ['app-misc/A']

		playground = ResolverPlayground(binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()

	def testSonameSlotConflictMixedDependencies(self):
		"""
		Bug 487198
		For parents with mixed >= and < dependencies, we scheduled
		reinstalls for the >= atom, but in the end didn't install the
		child update because of the < atom.
		"""
		binpkgs = {
			"cat/slotted-lib-1" : {
				"PROVIDES": "x86_32: lib1.so",
				"SLOT": "1",
			},
			"cat/slotted-lib-2" : {
				"PROVIDES": "x86_32: lib2.so",
				"SLOT": "2",
			},
			"cat/slotted-lib-3" : {
				"PROVIDES": "x86_32: lib3.so",
				"SLOT": "3",
			},
			"cat/slotted-lib-4" : {
				"PROVIDES": "x86_32: lib4.so",
				"SLOT": "4",
			},
			"cat/slotted-lib-5" : {
				"PROVIDES": "x86_32: lib5.so",
				"SLOT": "5",
			},
			"cat/user-1" : {
				"DEPEND": ">=cat/slotted-lib-2 <cat/slotted-lib-4",
				"RDEPEND": ">=cat/slotted-lib-2 <cat/slotted-lib-4",
				"REQUIRES": "x86_32: lib3.so",
			},
		}

		installed = {
			"cat/slotted-lib-3" : {
				"PROVIDES": "x86_32: lib3.so",
				"SLOT": "3",
			},
			"cat/user-1" : {
				"DEPEND": ">=cat/slotted-lib-2 <cat/slotted-lib-4",
				"RDEPEND": ">=cat/slotted-lib-2 <cat/slotted-lib-4",
				"REQUIRES": "x86_32: lib3.so",
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["cat/user"],
				options = {
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True,
				},
				success = True,
				mergelist = []),
		)

		world = []

		playground = ResolverPlayground(binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success,
					True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
