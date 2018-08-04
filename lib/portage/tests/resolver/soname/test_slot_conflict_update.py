# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground, ResolverPlaygroundTestCase)

class SonameSlotConflictUpdateTestCase(TestCase):

	def testSonameSlotConflictUpdate(self):

		binpkgs = {

			"app-text/podofo-0.9.2" : {
				"RDEPEND" : "dev-util/boost-build",
			},

			"dev-cpp/libcmis-0.3.1" : {
				"DEPEND": "dev-libs/boost",
				"RDEPEND": "dev-libs/boost",
				"REQUIRES": "x86_32: libboost-1.53.so",
			},

			"dev-libs/boost-1.53.0" : {
				"PROVIDES": "x86_32: libboost-1.53.so",
				"RDEPEND" : "=dev-util/boost-build-1.53.0",
			},

			"dev-libs/boost-1.52.0" : {
				"PROVIDES": "x86_32: libboost-1.52.so",
				"RDEPEND" : "=dev-util/boost-build-1.52.0",
			},

			"dev-util/boost-build-1.53.0" : {
			},

			"dev-util/boost-build-1.52.0" : {
			},


		}

		installed = {

			"app-text/podofo-0.9.2" : {
				"RDEPEND" : "dev-util/boost-build",
			},

			"dev-cpp/libcmis-0.3.1" : {
				"DEPEND": "dev-libs/boost",
				"RDEPEND": "dev-libs/boost",
				"REQUIRES": "x86_32: libboost-1.52.so",
			},

			"dev-util/boost-build-1.52.0" : {
			},

			"dev-libs/boost-1.52.0" : {
				"PROVIDES": "x86_32: libboost-1.52.so",
				"RDEPEND" : "=dev-util/boost-build-1.52.0",
			},

		}

		world = [
			"dev-cpp/libcmis",
			"dev-libs/boost",
			"app-text/podofo",
		]

		test_cases = (

			ResolverPlaygroundTestCase(
				world,
				all_permutations = True,
				options = {
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					'[binary]dev-util/boost-build-1.53.0',
					'[binary]dev-libs/boost-1.53.0',
					'[binary]dev-cpp/libcmis-0.3.1'
				]
			),

			ResolverPlaygroundTestCase(
				world,
				all_permutations = True,
				options = {
					"--deep": True,
					"--ignore-soname-deps": "y",
					"--update": True,
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					'[binary]dev-util/boost-build-1.53.0',
					'[binary]dev-libs/boost-1.53.0',
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
