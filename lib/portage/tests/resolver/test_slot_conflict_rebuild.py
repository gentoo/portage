# Copyright 2012-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotConflictRebuildTestCase(TestCase):

	def testSlotConflictRebuild(self):

		ebuilds = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/A-2" : {
				"EAPI": "5",
				"SLOT": "0/2"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"DEPEND": "app-misc/A:=",
				"RDEPEND": "app-misc/A:="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"DEPEND": "<app-misc/A-2",
				"RDEPEND": "<app-misc/A-2"
			},

			"app-misc/D-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/D-2" : {
				"EAPI": "5",
				"SLOT": "0/2"
			},

			"app-misc/E-0" : {
				"EAPI": "5",
				"DEPEND": "app-misc/D:=",
				"RDEPEND": "app-misc/D:="
			},

		}

		installed = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"DEPEND": "app-misc/A:0/1=",
				"RDEPEND": "app-misc/A:0/1="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"DEPEND": "<app-misc/A-2",
				"RDEPEND": "<app-misc/A-2"
			},

			"app-misc/D-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/E-0" : {
				"EAPI": "5",
				"DEPEND": "app-misc/D:0/1=",
				"RDEPEND": "app-misc/D:0/1="
			},

		}

		world = ["app-misc/B", "app-misc/C", "app-misc/E"]

		test_cases = (

			# Test bug #439688, where a slot conflict prevents an
			# upgrade and we don't want to trigger unnecessary rebuilds.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--backtrack": 4},
				success = True,
				mergelist = ["app-misc/D-2", "app-misc/E-0"]),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testSlotConflictMassRebuild(self):
		"""
		Bug 486580
		Before this bug was fixed, emerge would backtrack for each package that needs
		a rebuild. This could cause it to hit the backtrack limit and not rebuild all
		needed packages.
		"""
		ebuilds = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"DEPEND": "app-misc/B:=",
				"RDEPEND": "app-misc/B:="
			},

			"app-misc/B-1" : {
				"EAPI": "5",
				"SLOT": "1"
			},

			"app-misc/B-2" : {
				"EAPI": "5",
				"SLOT": "2/2"
			},
		}

		installed = {
			"app-misc/B-1" : {
				"EAPI": "5",
				"SLOT": "1"
			},
		}

		expected_mergelist = ['app-misc/A-1', 'app-misc/B-2']

		for i in range(5):
			ebuilds["app-misc/C%sC-1" % i] = {
				"EAPI": "5",
				"DEPEND": "app-misc/B:=",
				"RDEPEND": "app-misc/B:="
			}

			installed["app-misc/C%sC-1" % i] = {
				"EAPI": "5",
				"DEPEND": "app-misc/B:1/1=",
				"RDEPEND": "app-misc/B:1/1="
			}
			for x in ("DEPEND", "RDEPEND"):
				ebuilds["app-misc/A-1"][x] += " app-misc/C%sC" % i

			expected_mergelist.append("app-misc/C%sC-1" % i)


		test_cases = (
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				ignore_mergelist_order=True,
				all_permutations=True,
				options = {"--backtrack": 3, '--update': True, '--deep': True},
				success = True,
				mergelist = expected_mergelist),
		)

		world = []

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testSlotConflictForgottenChild(self):
		"""
		Similar to testSlotConflictMassRebuild above, but this time the rebuilds are scheduled,
		but the package causing the rebuild (the child) is not installed.
		"""
		ebuilds = {

			"app-misc/A-2" : {
				"EAPI": "5",
				"DEPEND": "app-misc/B:= app-misc/C",
				"RDEPEND": "app-misc/B:= app-misc/C",
			},

			"app-misc/B-2" : {
				"EAPI": "5",
				"SLOT": "2"
			},

			"app-misc/C-1": {
				"EAPI": "5",
				"DEPEND": "app-misc/B:=",
				"RDEPEND": "app-misc/B:="
			},
		}

		installed = {
			"app-misc/A-1" : {
				"EAPI": "5",
				"DEPEND": "app-misc/B:1/1= app-misc/C",
				"RDEPEND": "app-misc/B:1/1= app-misc/C",
			},

			"app-misc/B-1" : {
				"EAPI": "5",
				"SLOT": "1"
			},

			"app-misc/C-1": {
				"EAPI": "5",
				"DEPEND": "app-misc/B:1/1=",
				"RDEPEND": "app-misc/B:1/1="
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				success = True,
				mergelist = ['app-misc/A-2']),

			ResolverPlaygroundTestCase(
				["app-misc/A"],
				options={"--update": True, "--deep": True},
				success = True,
				mergelist = ['app-misc/B-2', 'app-misc/C-1', 'app-misc/A-2']),
		)

		world = []

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testSlotConflictDepChange(self):
		"""
		Bug 490362
		The dependency in the ebuild was changed form slot operator to
		no slot operator. The vdb contained the slot operator and emerge
		would refuse to rebuild.
		"""
		ebuilds = {
			"app-misc/A-1" : {
				"EAPI": "5",
				"DEPEND": "app-misc/B",
				"RDEPEND": "app-misc/B"
			},

			"app-misc/B-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/B-2" : {
				"EAPI": "5",
				"SLOT": "0/2"
			},
		}

		installed = {
			"app-misc/A-1" : {
				"EAPI": "5",
				"DEPEND": "app-misc/B:0/1=",
				"RDEPEND": "app-misc/B:0/1="
			},
			"app-misc/B-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["app-misc/B"],
				success = True,
				mergelist = ['app-misc/B-2', 'app-misc/A-1']),
		)

		world = ["app-misc/A"]

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testSlotConflictMixedDependencies(self):
		"""
		Bug 487198
		For parents with mixed >= and < dependencies, we scheduled rebuilds for the
		>= atom, but in the end didn't install the child update because of the < atom.
		"""
		ebuilds = {
			"cat/slotted-lib-1" : {
				"EAPI": "5",
				"SLOT": "1"
			},
			"cat/slotted-lib-2" : {
				"EAPI": "5",
				"SLOT": "2"
			},
			"cat/slotted-lib-3" : {
				"EAPI": "5",
				"SLOT": "3"
			},
			"cat/slotted-lib-4" : {
				"EAPI": "5",
				"SLOT": "4"
			},
			"cat/slotted-lib-5" : {
				"EAPI": "5",
				"SLOT": "5"
			},
			"cat/user-1" : {
				"EAPI": "5",
				"DEPEND": ">=cat/slotted-lib-2:= <cat/slotted-lib-4:=",
				"RDEPEND": ">=cat/slotted-lib-2:= <cat/slotted-lib-4:=",
			},
		}

		installed = {
			"cat/slotted-lib-3" : {
				"EAPI": "5",
				"SLOT": "3"
			},
			"cat/user-1" : {
				"EAPI": "5",
				"DEPEND": ">=cat/slotted-lib-2:3/3= <cat/slotted-lib-4:3/3=",
				"RDEPEND": ">=cat/slotted-lib-2:3/3= <cat/slotted-lib-4:3/3=",
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["cat/user"],
				options = {"--deep": True, "--update": True},
				success = True,
				mergelist = []),
		)

		world = []

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testSlotConflictMultiRepo(self):
		"""
		Bug 497238
		Different repositories contain the same cpv with different sub-slots for
		a slot operator child.
		Downgrading the slot operator parent would result in a sub-slot change of
		the installed package by changing the source repository.
		Make sure we don't perform this undesirable rebuild.
		"""
		ebuilds = {
			"net-firewall/iptables-1.4.21::overlay" : { "EAPI": "5", "SLOT": "0/10" },
			"sys-apps/iproute2-3.11.0::overlay" : { "EAPI": "5", "RDEPEND": "net-firewall/iptables:=" },

			"net-firewall/iptables-1.4.21" : { "EAPI": "5", "SLOT": "0" },
			"sys-apps/iproute2-3.12.0": { "EAPI": "5", "RDEPEND": "net-firewall/iptables:=" },
		}

		installed = {
			"net-firewall/iptables-1.4.21::overlay" : { "EAPI": "5", "SLOT": "0/10" },
			"sys-apps/iproute2-3.12.0": { "EAPI": "5", "RDEPEND": "net-firewall/iptables:0/10=" },
		}

		world = ["sys-apps/iproute2"]

		test_cases = (
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--deep": True, "--update": True, "--verbose": True},
				success = True,
				mergelist = []),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testSlotConflictMultiRepoUpdates(self):
		"""
		Bug 508236 (similar to testSlotConflictMultiRepo)
		Different repositories contain the same cpv with different sub-slots for
		a slot operator child. For both the installed version and an updated version.

		"""
		ebuilds = {
			"net-firewall/iptables-1.4.21::overlay" : { "EAPI": "5", "SLOT": "0/10" },
			"net-firewall/iptables-1.4.21-r1::overlay" : { "EAPI": "5", "SLOT": "0/10" },
			"sys-apps/iproute2-3.11.0::overlay" : { "EAPI": "5", "RDEPEND": "net-firewall/iptables:=" },

			"net-firewall/iptables-1.4.21" : { "EAPI": "5", "SLOT": "0" },
			"net-firewall/iptables-1.4.21-r1" : { "EAPI": "5", "SLOT": "0" },
			"sys-apps/iproute2-3.12.0": { "EAPI": "5", "RDEPEND": "net-firewall/iptables:=" },
		}

		installed = {
			"net-firewall/iptables-1.4.21::overlay" : { "EAPI": "5", "SLOT": "0/10" },
			"sys-apps/iproute2-3.12.0": { "EAPI": "5", "RDEPEND": "net-firewall/iptables:0/10=" },
		}

		world = ["sys-apps/iproute2"]

		test_cases = (
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--deep": True, "--update": True, "--verbose": True},
				success = True,
				mergelist = ["net-firewall/iptables-1.4.21-r1::overlay"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testSlotConflictRebuildGolang(self):

		ebuilds = {

			"dev-lang/go-1.14.7" : {
				"EAPI": "7",
				"SLOT": "0/1.14.7"
			},

			"dev-lang/go-1.15" : {
				"EAPI": "7",
				"SLOT": "0/1.15"
			},

			"net-p2p/syncthing-1.3.4-r1" : {
				"EAPI": "7",
				"BDEPEND": "=dev-lang/go-1.14* >=dev-lang/go-1.12"
			},

		}

		installed = {

			"dev-lang/go-1.14.7" : {
				"EAPI": "7",
				"SLOT": "0/1.14.7"
			},

			"net-p2p/syncthing-1.3.4-r1" : {
				"EAPI": "7",
				"BDEPEND": "=dev-lang/go-1.14* >=dev-lang/go-1.12"
			},

		}

		world = ["dev-lang/go", "net-p2p/syncthing"]

		test_cases = (

			# Demonstrate an unwanted dev-lang/go rebuild triggered by a missed
			# update due to a slot conflict (bug #439688).
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = []),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
