# Copyright 2017-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class SlotOperatorRuntimePkgMaskTestCase(TestCase):

	def testSlotOperatorRuntimePkgMask(self):

		ebuilds = {
			"app-misc/meta-pkg-2" : {
				"EAPI": "6",
				"DEPEND": "=app-misc/B-2 =app-misc/C-1  =app-misc/D-1 =dev-libs/foo-2",
				"RDEPEND": "=app-misc/B-2 =app-misc/C-1 =app-misc/D-1 =dev-libs/foo-2",
			},

			"app-misc/meta-pkg-1" : {
				"EAPI": "6",
				"DEPEND": "=app-misc/B-1 =app-misc/C-1  =app-misc/D-1 =dev-libs/foo-1",
				"RDEPEND": "=app-misc/B-1 =app-misc/C-1 =app-misc/D-1 =dev-libs/foo-1",
			},

			"app-misc/B-1" : {
				"EAPI": "6",
				"DEPEND": "dev-libs/foo:=",
				"RDEPEND": "dev-libs/foo:=",
			},

			"app-misc/B-2" : {
				"EAPI": "6",
				"DEPEND": "dev-libs/foo:=",
				"RDEPEND": "dev-libs/foo:=",
			},

			"app-misc/C-1" : {
				"EAPI": "6",
				"DEPEND": "dev-libs/foo:=",
				"RDEPEND": "dev-libs/foo:=",
			},

			"app-misc/C-2" : {
				"EAPI": "6",
				"DEPEND": "dev-libs/foo:=",
				"RDEPEND": "dev-libs/foo:=",
			},

			"app-misc/D-1" : {
				"EAPI": "6",
				"DEPEND": "dev-libs/foo:=",
				"RDEPEND": "dev-libs/foo:=",
			},

			"app-misc/D-2" : {
				"EAPI": "6",
				"DEPEND": "dev-libs/foo:=",
				"RDEPEND": "dev-libs/foo:=",
			},

			"dev-libs/foo-1" : {
				"EAPI": "6",
				"SLOT": "0/1",
			},

			"dev-libs/foo-2" : {
				"EAPI": "6",
				"SLOT": "0/2",
			},
		}

		installed = {
			"app-misc/meta-pkg-1" : {
				"EAPI": "6",
				"DEPEND": "=app-misc/B-1 =app-misc/C-1  =app-misc/D-1 =dev-libs/foo-1",
				"RDEPEND": "=app-misc/B-1 =app-misc/C-1 =app-misc/D-1 =dev-libs/foo-1",
			},

			"app-misc/B-1" : {
				"EAPI": "6",
				"DEPEND": "dev-libs/foo:0/1=",
				"RDEPEND": "dev-libs/foo:0/1=",
			},

			"app-misc/C-1" : {
				"EAPI": "6",
				"DEPEND": "dev-libs/foo:0/1=",
				"RDEPEND": "dev-libs/foo:0/1=",
			},

			"app-misc/D-1" : {
				"EAPI": "6",
				"DEPEND": "dev-libs/foo:0/1=",
				"RDEPEND": "dev-libs/foo:0/1=",
			},

			"dev-libs/foo-1" : {
				"EAPI": "6",
				"SLOT": "0/1",
			},
		}

		world = (
			"app-misc/meta-pkg",
		)

		test_cases = (
			ResolverPlaygroundTestCase(
				["=app-misc/meta-pkg-2"],
				options = {
					"--backtrack": 14,
				},
				success = True,
				ambiguous_merge_order = True,
				mergelist = [
					'dev-libs/foo-2',
					('app-misc/D-1', 'app-misc/C-1', 'app-misc/B-2'),
					'app-misc/meta-pkg-2',
				]
			),
		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed,
			world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			playground.debug = False
			playground.cleanup()
