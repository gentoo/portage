# Copyright 2016-2021 Gentoo Authors
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


class SlotOperatorReverseDepsLibGit2TestCase(TestCase):

	def testSlotOperatorReverseDepsLibGit2(self):
		"""
		Test bug #717140, where the depgraph _slot_operator_update_probe
		method ignored <dev-libs/libgit2-1:0= dependency and tried to
		trigger an upgrade to dev-libs/libgit2-1.0.0-r1, ultimately
		resulting in an undesirable downgrade to dev-libs/libgit2-0.28.4-r1.
		"""

		ebuilds = {

			"dev-libs/libgit2-0.28.4-r1" : {
				"EAPI": "7",
				"SLOT": "0/28",
			},

			"dev-libs/libgit2-0.99.0-r1" : {
				"EAPI": "7",
				"SLOT": "0/0.99",
			},

			"dev-libs/libgit2-1.0.0-r1" : {
				"EAPI": "7",
				"SLOT": "0/1.0",
			},

			"dev-libs/libgit2-glib-0.28.0.1" : {
				"EAPI": "7",
				"SLOT": "0",
				"RDEPEND": "<dev-libs/libgit2-0.29:0= >=dev-libs/libgit2-0.26.0",
			},

			"dev-libs/libgit2-glib-0.99.0.1" : {
				"EAPI": "7",
				"SLOT": "0",
				"RDEPEND": "<dev-libs/libgit2-1:0= >=dev-libs/libgit2-0.26.0",
			},

			"dev-vcs/gitg-3.32.1-r1" : {
				"EAPI": "7",
				"SLOT": "0",
				"RDEPEND": "dev-libs/libgit2:= >=dev-libs/libgit2-glib-0.27 <dev-libs/libgit2-glib-1",
			},
		}

		installed = {

			"dev-libs/libgit2-0.99.0-r1" : {
				"EAPI": "7",
				"SLOT": "0/0.99",
			},

			"dev-libs/libgit2-glib-0.99.0.1" : {
				"EAPI": "7",
				"SLOT": "0",
				"RDEPEND": "<dev-libs/libgit2-1:0/0.99= >=dev-libs/libgit2-0.26.0",
			},

			"dev-vcs/gitg-3.32.1-r1" : {
				"EAPI": "7",
				"SLOT": "0",
				"RDEPEND": "dev-libs/libgit2:0/0.99= >=dev-libs/libgit2-glib-0.27 <dev-libs/libgit2-glib-1",
			},

		}

		world = ["dev-vcs/gitg"]

		test_cases = (
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				#mergelist = ['dev-libs/libgit2-0.28.4-r1', 'dev-libs/libgit2-glib-0.99.0.1', 'dev-vcs/gitg-3.32.1-r1'],
				mergelist = [],
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
			playground.debug = False
			playground.cleanup()


class SlotOperatorReverseDepsVirtualTestCase(TestCase):

	def testSlotOperatorReverseDepsVirtual(self):
		"""
		Demonstrate bug #764764, where slot operator rebuilds were
		not triggered for reverse deps of virtual/dist-kernel.
		"""

		ebuilds = {

			"app-emulation/virtualbox-modules-6.1.16-r1": {
				"EAPI": "7",
				"DEPEND": "virtual/dist-kernel",
				"RDEPEND": "virtual/dist-kernel:=",
			},

			"sys-kernel/gentoo-kernel-5.10.6": {
				"EAPI": "7",
				"SLOT": "5.10.6",
			},

			"sys-kernel/gentoo-kernel-5.10.5": {
				"EAPI": "7",
				"SLOT": "5.10.5",
			},

			"virtual/dist-kernel-5.10.5" : {
				"EAPI": "7",
				"SLOT": "0/5.10.5",
				"RDEPEND": "~sys-kernel/gentoo-kernel-5.10.5",
			},

			"virtual/dist-kernel-5.10.6" : {
				"EAPI": "7",
				"SLOT": "0/5.10.6",
				"RDEPEND": "~sys-kernel/gentoo-kernel-5.10.6"
			},

			"x11-drivers/nvidia-drivers-460.32.03" : {
				"EAPI": "7",
				"DEPEND": "virtual/dist-kernel",
				"RDEPEND": "virtual/dist-kernel:=",
			},

		}

		installed = {

			"app-emulation/virtualbox-modules-6.1.16-r1": {
				"EAPI": "7",
				"DEPEND": "virtual/dist-kernel",
				"RDEPEND": "virtual/dist-kernel:0/5.10.5=",
			},

			"sys-kernel/gentoo-kernel-5.10.5": {
				"EAPI": "7",
				"SLOT": "5.10.5",
			},

			"virtual/dist-kernel-5.10.5" : {
				"EAPI": "7",
				"SLOT": "0/5.10.5",
				"RDEPEND": "~sys-kernel/gentoo-kernel-5.10.5"
			},

			"x11-drivers/nvidia-drivers-460.32.03" : {
				"EAPI": "7",
				"DEPEND": "virtual/dist-kernel",
				"RDEPEND": "virtual/dist-kernel:0/5.10.5="
			},

		}

		world = ["app-emulation/virtualbox-modules", "x11-drivers/nvidia-drivers"]

		test_cases = (
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ['sys-kernel/gentoo-kernel-5.10.6', 'virtual/dist-kernel-5.10.6', 'app-emulation/virtualbox-modules-6.1.16-r1', 'x11-drivers/nvidia-drivers-460.32.03']
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
			playground.debug = False
			playground.cleanup()
