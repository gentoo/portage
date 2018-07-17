# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class SlotOperatorExclusiveSlotsTestCase(TestCase):

	def testSlotOperatorExclusiveSlots(self):

		ebuilds = {

			"media-libs/mesa-17.0.1" : {
				"EAPI": "6",
				"SLOT": "0",
				"RDEPEND": "<sys-devel/llvm-5:="
			},

			"sys-devel/clang-4.0.0" : {
				"EAPI": "6",
				"SLOT": "4",
				"RDEPEND": ("~sys-devel/llvm-4.0.0:4= "
					"!sys-devel/llvm:0 !sys-devel/clang:0"),
			},

			"sys-devel/clang-3.9.1-r100" : {
				"EAPI": "6",
				"SLOT": "0/3.9.1",
				"RDEPEND": "~sys-devel/llvm-3.9.1",
			},

			"sys-devel/llvm-4.0.0" : {
				"EAPI": "6",
				"SLOT": "4",
				"RDEPEND": "!sys-devel/llvm:0",
			},

			"sys-devel/llvm-3.9.1" : {
				"EAPI": "6",
				"SLOT": "0/3.91",
				"RDEPEND": "!sys-devel/llvm:0",
				"PDEPEND": "=sys-devel/clang-3.9.1-r100",
			},

		}

		installed = {

			"media-libs/mesa-17.0.1" : {
				"EAPI": "6",
				"SLOT": "0",
				"RDEPEND": "<sys-devel/llvm-5:0/3.9.1="
			},

			"sys-devel/clang-3.9.1-r100" : {
				"EAPI": "6",
				"SLOT": "0/3.9.1",
				"RDEPEND": "~sys-devel/llvm-3.9.1",
			},

			"sys-devel/llvm-3.9.1" : {
				"EAPI": "6",
				"SLOT": "0/3.9.1",
				"RDEPEND": "!sys-devel/llvm:0",
				"PDEPEND": "=sys-devel/clang-3.9.1-r100",
			},

		}

		world = ["sys-devel/clang", "media-libs/mesa"]

		test_cases = (

			# Test bug #612772, where slot operator rebuilds are not
			# properly triggered (for things like mesa) during a
			# llvm:0 to llvm:4 upgrade with clang, resulting in
			# unsolved blockers.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				ambiguous_merge_order = True,
				mergelist = [
					'sys-devel/llvm-4.0.0',
					'media-libs/mesa-17.0.1',
					(
						'sys-devel/clang-4.0.0',
						'[uninstall]sys-devel/llvm-3.9.1',
						'!sys-devel/llvm:0',
						'[uninstall]sys-devel/clang-3.9.1-r100',
						'!sys-devel/clang:0',
					)
				],
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.cleanup()


		world = ["media-libs/mesa"]

		test_cases = (

			# Test bug #612874, where a direct circular dependency
			# between llvm-3.9.1 and clang-3.9.1-r100 causes a
			# missed update from llvm:0 to llvm:4. Since llvm:4 does
			# not have a dependency on clang, the upgrade from llvm:0
			# to llvm:4 makes the installed sys-devel/clang-3.9.1-r100
			# instance eligible for removal by emerge --depclean, which
			# explains why clang does not appear in the mergelist.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				ambiguous_merge_order = True,
				mergelist = [
					'sys-devel/llvm-4.0.0',
					(
						'media-libs/mesa-17.0.1',
						'[uninstall]sys-devel/llvm-3.9.1',
						'!sys-devel/llvm:0',
					)
				],
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.cleanup()
