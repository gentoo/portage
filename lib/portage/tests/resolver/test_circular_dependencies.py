# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class CircularDependencyTestCase(TestCase):

	#TODO:
	#	use config change by autounmask
	#	conflict on parent's parent
	#	difference in RDEPEND and DEPEND
	#	is there anything else than priority buildtime and runtime?
	#	play with use.{mask,force}
	#	play with REQUIRED_USE


	def testCircularDependency(self):

		ebuilds = {
			"dev-libs/Z-1": { "DEPEND": "foo? ( !bar? ( dev-libs/Y ) )", "IUSE": "+foo bar", "EAPI": 1 },
			"dev-libs/Z-2": { "DEPEND": "foo? ( dev-libs/Y ) !bar? ( dev-libs/Y )", "IUSE": "+foo bar", "EAPI": 1 },
			"dev-libs/Z-3": { "DEPEND": "foo? ( !bar? ( dev-libs/Y ) ) foo? ( dev-libs/Y ) !bar? ( dev-libs/Y )", "IUSE": "+foo bar", "EAPI": 1 },
			"dev-libs/Y-1": { "DEPEND": "dev-libs/Z" },
			"dev-libs/W-1": { "DEPEND": "dev-libs/Z[foo] dev-libs/Y", "EAPI": 2 },
			"dev-libs/W-2": { "DEPEND": "dev-libs/Z[foo=] dev-libs/Y", "IUSE": "+foo", "EAPI": 2 },
			"dev-libs/W-3": { "DEPEND": "dev-libs/Z[bar] dev-libs/Y", "EAPI": 2 },

			"app-misc/A-1": { "DEPEND": "foo? ( =app-misc/B-1 )", "IUSE": "+foo bar", "REQUIRED_USE": "^^ ( foo bar )", "EAPI": "4" },
			"app-misc/A-2": { "DEPEND": "foo? ( =app-misc/B-2 ) bar? ( =app-misc/B-2 )", "IUSE": "+foo bar", "REQUIRED_USE": "^^ ( foo bar )", "EAPI": "4" },
			"app-misc/B-1": { "DEPEND": "=app-misc/A-1" },
			"app-misc/B-2": { "DEPEND": "=app-misc/A-2" },
			}

		test_cases = (
			#Simple tests
			ResolverPlaygroundTestCase(
				["=dev-libs/Z-1"],
				circular_dependency_solutions = { "dev-libs/Y-1": frozenset([frozenset([("foo", False)]), frozenset([("bar", True)])])},
				success = False),
			ResolverPlaygroundTestCase(
				["=dev-libs/Z-2"],
				circular_dependency_solutions = { "dev-libs/Y-1": frozenset([frozenset([("foo", False), ("bar", True)])])},
				success = False),
			ResolverPlaygroundTestCase(
				["=dev-libs/Z-3"],
				circular_dependency_solutions = { "dev-libs/Y-1": frozenset([frozenset([("foo", False), ("bar", True)])])},
				success = False),

			#Conflict on parent
			ResolverPlaygroundTestCase(
				["=dev-libs/W-1"],
				circular_dependency_solutions = {},
				success = False),
			ResolverPlaygroundTestCase(
				["=dev-libs/W-2"],
				circular_dependency_solutions = { "dev-libs/Y-1": frozenset([frozenset([("foo", False), ("bar", True)])])},
				success = False),

			#Conflict with autounmask
			ResolverPlaygroundTestCase(
				["=dev-libs/W-3"],
				circular_dependency_solutions = { "dev-libs/Y-1": frozenset([frozenset([("foo", False)])])},
				use_changes = { "dev-libs/Z-3": {"bar": True}},
				success = False),

			#Conflict with REQUIRED_USE
			ResolverPlaygroundTestCase(
				["=app-misc/B-1"],
				circular_dependency_solutions = { "app-misc/B-1": frozenset([frozenset([("foo", False), ("bar", True)])])},
				success = False),
			ResolverPlaygroundTestCase(
				["=app-misc/B-2"],
				circular_dependency_solutions = {},
				success = False),
		)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
