# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class SimpleDepcleanTestCase(TestCase):

	def testSimpleDepclean(self):
		ebuilds = {
			"dev-libs/A-1": {},
			"dev-libs/B-1": {},
			}
		installed = {
			"dev-libs/A-1": {},
			"dev-libs/B-1": {},
			}

		world = (
			"dev-libs/A",
			)

		test_cases = (
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				cleanlist=["dev-libs/B-1"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

class DepcleanWithDepsTestCase(TestCase):

	def testDepcleanWithDeps(self):
		ebuilds = {
			"dev-libs/A-1": { "RDEPEND": "dev-libs/C" },
			"dev-libs/B-1": { "RDEPEND": "dev-libs/D" },
			"dev-libs/C-1": {},
			"dev-libs/D-1": { "RDEPEND": "dev-libs/E" },
			"dev-libs/E-1": { "RDEPEND": "dev-libs/F" },
			"dev-libs/F-1": {},
			}
		installed = {
			"dev-libs/A-1": { "RDEPEND": "dev-libs/C" },
			"dev-libs/B-1": { "RDEPEND": "dev-libs/D" },
			"dev-libs/C-1": {},
			"dev-libs/D-1": { "RDEPEND": "dev-libs/E" },
			"dev-libs/E-1": { "RDEPEND": "dev-libs/F" },
			"dev-libs/F-1": {},
			}

		world = (
			"dev-libs/A",
			)

		test_cases = (
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				cleanlist=["dev-libs/B-1", "dev-libs/D-1",
					"dev-libs/E-1", "dev-libs/F-1"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


class DepcleanWithInstalledMaskedTestCase(TestCase):

	def testDepcleanWithInstalledMasked(self):
		"""
		Test case for bug 332719.
		emerge --declean ignores that B is masked by license and removes C.
		The next emerge -uDN world doesn't take B and installs C again.
		"""
		ebuilds = {
			"dev-libs/A-1": { "RDEPEND": "|| ( dev-libs/B dev-libs/C )" },
			"dev-libs/B-1": { "LICENSE": "TEST", "KEYWORDS": "x86" },
			"dev-libs/C-1": { "KEYWORDS": "x86" },
			}
		installed = {
			"dev-libs/A-1": { "RDEPEND": "|| ( dev-libs/B dev-libs/C )" },
			"dev-libs/B-1": { "LICENSE": "TEST", "KEYWORDS": "x86" },
			"dev-libs/C-1": { "KEYWORDS": "x86" },
			}

		world = (
			"dev-libs/A",
			)

		test_cases = (
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				#cleanlist=["dev-libs/C-1"]),
				cleanlist=["dev-libs/B-1"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

class DepcleanInstalledKeywordMaskedSlotTestCase(TestCase):

	def testDepcleanInstalledKeywordMaskedSlot(self):
		"""
		Verify that depclean removes newer slot
		masked by KEYWORDS (see bug #350285).
		"""
		ebuilds = {
			"dev-libs/A-1": { "RDEPEND": "|| ( =dev-libs/B-2.7* =dev-libs/B-2.6* )" },
			"dev-libs/B-2.6": { "SLOT":"2.6", "KEYWORDS": "x86" },
			"dev-libs/B-2.7": { "SLOT":"2.7", "KEYWORDS": "~x86" },
			}
		installed = {
			"dev-libs/A-1": { "EAPI" : "3", "RDEPEND": "|| ( dev-libs/B:2.7 dev-libs/B:2.6 )" },
			"dev-libs/B-2.6": { "SLOT":"2.6", "KEYWORDS": "x86" },
			"dev-libs/B-2.7": { "SLOT":"2.7", "KEYWORDS": "~x86" },
			}

		world = (
			"dev-libs/A",
			)

		test_cases = (
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				cleanlist=["dev-libs/B-2.7"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

class DepcleanWithExcludeTestCase(TestCase):

	def testDepcleanWithExclude(self):

		installed = {
			"dev-libs/A-1": {},
			"dev-libs/B-1": { "RDEPEND": "dev-libs/A" },
			}

		# depclean asserts non-empty @world set
		world = ["non-empty/world-set"]

		test_cases = (
			#Without --exclude.
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				cleanlist=["dev-libs/B-1", "dev-libs/A-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options={"--depclean": True},
				success=True,
				cleanlist=[]),
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options={"--depclean": True},
				success=True,
				cleanlist=["dev-libs/B-1"]),

			#With --exclude
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True, "--exclude": ["dev-libs/A"]},
				success=True,
				cleanlist=["dev-libs/B-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options={"--depclean": True, "--exclude": ["dev-libs/B"]},
				success=True,
				cleanlist=[]),
			)

		playground = ResolverPlayground(installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

class DepcleanWithExcludeAndSlotsTestCase(TestCase):

	def testDepcleanWithExcludeAndSlots(self):

		installed = {
			"dev-libs/Z-1": { "SLOT": 1},
			"dev-libs/Z-2": { "SLOT": 2},
			"dev-libs/Y-1": { "RDEPEND": "=dev-libs/Z-1", "SLOT": 1 },
			"dev-libs/Y-2": { "RDEPEND": "=dev-libs/Z-2", "SLOT": 2 },
			}

		world=["dev-libs/Y"]

		test_cases = (
			#Without --exclude.
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				cleanlist=["dev-libs/Y-1", "dev-libs/Z-1"]),
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True, "--exclude": ["dev-libs/Z"]},
				success=True,
				cleanlist=["dev-libs/Y-1"]),
			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True, "--exclude": ["dev-libs/Y"]},
				success=True,
				cleanlist=[]),
			)

		playground = ResolverPlayground(installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

class DepcleanAndWildcardsTestCase(TestCase):

	def testDepcleanAndWildcards(self):

		installed = {
			"dev-libs/A-1": { "RDEPEND": "dev-libs/B" },
			"dev-libs/B-1": {},
			}

		# depclean asserts non-empty @world set
		world = ["non-empty/world-set"]

		test_cases = (
			ResolverPlaygroundTestCase(
				["*/*"],
				options={"--depclean": True},
				success=True,
				cleanlist=["dev-libs/A-1", "dev-libs/B-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/*"],
				options={"--depclean": True},
				success=True,
				cleanlist=["dev-libs/A-1", "dev-libs/B-1"]),
			ResolverPlaygroundTestCase(
				["*/A"],
				options={"--depclean": True},
				success=True,
				cleanlist=["dev-libs/A-1"]),
			ResolverPlaygroundTestCase(
				["*/B"],
				options={"--depclean": True},
				success=True,
				cleanlist=[]),
			)

		playground = ResolverPlayground(installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
