# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotConflictUpdateTestCase(TestCase):

	def testSlotConflictUpdate(self):

		ebuilds = {

			"app-text/podofo-0.9.2" : {
				"EAPI": "5",
				"RDEPEND" : "dev-util/boost-build"
			},

			"dev-cpp/libcmis-0.3.1" : {
				"EAPI": "5",
				"RDEPEND" : "dev-libs/boost:="
			},

			"dev-libs/boost-1.53.0" : {
				"EAPI": "5",
				"SLOT": "0/1.53",
				"RDEPEND" : "=dev-util/boost-build-1.53.0"
			},

			"dev-libs/boost-1.52.0" : {
				"EAPI": "5",
				"SLOT": "0/1.52",
				"RDEPEND" : "=dev-util/boost-build-1.52.0"
			},

			"dev-util/boost-build-1.53.0" : {
				"EAPI": "5",
				"SLOT": "0"
			},

			"dev-util/boost-build-1.52.0" : {
				"EAPI": "5",
				"SLOT": "0"
			},


		}

		installed = {

			"app-text/podofo-0.9.2" : {
				"EAPI": "5",
				"RDEPEND" : "dev-util/boost-build"
			},

			"dev-cpp/libcmis-0.3.1" : {
				"EAPI": "5",
				"RDEPEND" : "dev-libs/boost:0/1.52="
			},

			"dev-util/boost-build-1.52.0" : {
				"EAPI": "5",
				"SLOT": "0"
			},

			"dev-libs/boost-1.52.0" : {
				"EAPI": "5",
				"SLOT": "0/1.52",
				"RDEPEND" : "=dev-util/boost-build-1.52.0"
			}

		}

		world = ["dev-cpp/libcmis", "dev-libs/boost", "app-text/podofo"]

		test_cases = (

			# In order to avoid a missed update, first mask lower
			# versions that conflict with higher versions. Note that
			# this behavior makes SlotConflictMaskUpdateTestCase
			# fail.
			ResolverPlaygroundTestCase(
				['@world'],
				all_permutations = True,
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ['dev-util/boost-build-1.53.0', 'dev-libs/boost-1.53.0', 'dev-cpp/libcmis-0.3.1']),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
