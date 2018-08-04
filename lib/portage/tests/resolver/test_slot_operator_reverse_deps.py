# Copyright 2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class SlotOperatorReverseDepsTestCase(TestCase):

	def testSlotOperatorReverseDeps(self):

		ebuilds = {

			"media-libs/mesa-11.2.2" : {
				"EAPI": "6",
				"SLOT": "0",
				"RDEPEND": ">=sys-devel/llvm-3.6.0:="
			},

			"sys-devel/clang-3.7.1-r100" : {
				"EAPI": "6",
				"SLOT": "0/3.7",
				"RDEPEND": "~sys-devel/llvm-3.7.1"
			},

			"sys-devel/clang-3.8.0-r100" : {
				"EAPI": "6",
				"SLOT": "0/3.8",
				"RDEPEND": "~sys-devel/llvm-3.8.0"
			},

			"sys-devel/llvm-3.7.1-r2" : {
				"EAPI": "6",
				"SLOT": "0/3.7.1",
				"PDEPEND": "=sys-devel/clang-3.7.1-r100"
			},

			"sys-devel/llvm-3.8.0-r2" : {
				"EAPI": "6",
				"SLOT": "0/3.8.0",
				"PDEPEND": "=sys-devel/clang-3.8.0-r100"
			},

		}

		installed = {

			"media-libs/mesa-11.2.2" : {
				"EAPI": "6",
				"SLOT": "0",
				"RDEPEND": ">=sys-devel/llvm-3.6.0:0/3.7.1="
			},

			"sys-devel/clang-3.7.1-r100" : {
				"EAPI": "6",
				"SLOT": "0/3.7",
				"RDEPEND": "~sys-devel/llvm-3.7.1"
			},

			"sys-devel/llvm-3.7.1-r2" : {
				"EAPI": "6",
				"SLOT": "0/3.7.1",
				"PDEPEND": "=sys-devel/clang-3.7.1-r100"
			},

		}

		world = ["media-libs/mesa"]

		test_cases = (

			# Test bug #584626, where an llvm update is missed due to
			# the check_reverse_dependencies function seeing that
			# updating llvm will break a dependency of the installed
			# version of clang (though a clang update is available).
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = [
					'sys-devel/llvm-3.8.0-r2',
					'sys-devel/clang-3.8.0-r100',
					'media-libs/mesa-11.2.2',
				],
			),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--update": True,
					"--deep": True,
					"--ignore-built-slot-operator-deps": "y",
				},
				success = True,
				mergelist = [
					'sys-devel/llvm-3.8.0-r2',
					'sys-devel/clang-3.8.0-r100',
				],
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.cleanup()
