# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class AutounmaskTestCase(TestCase):

	def testAutounmask(self):

		ebuilds = {
			#ebuilds to test use changes
			"dev-libs/A-1": { "SLOT": 1, "DEPEND": "dev-libs/B[foo]", "EAPI": 2},
			"dev-libs/A-2": { "SLOT": 2, "DEPEND": "dev-libs/B[bar]", "EAPI": 2},
			"dev-libs/B-1": { "DEPEND": "foo? ( dev-libs/C ) bar? ( dev-libs/D )", "IUSE": "foo bar"},
			"dev-libs/C-1": {},
			"dev-libs/D-1": {},

			#ebuilds to test if we allow changing of masked or forced flags
			"dev-libs/E-1": { "SLOT": 1, "DEPEND": "dev-libs/F[masked-flag]", "EAPI": 2},
			"dev-libs/E-2": { "SLOT": 2, "DEPEND": "dev-libs/G[-forced-flag]", "EAPI": 2},
			"dev-libs/F-1": { "IUSE": "masked-flag"},
			"dev-libs/G-1": { "IUSE": "forced-flag"},

			#ebuilds to test keyword changes
			"app-misc/Z-1": { "KEYWORDS": "~x86", "DEPEND": "app-misc/Y" },
			"app-misc/Y-1": { "KEYWORDS": "~x86" },
			"app-misc/W-1": {},
			"app-misc/W-2": { "KEYWORDS": "~x86" },
			"app-misc/V-1": { "KEYWORDS": "~x86", "DEPEND": ">=app-misc/W-2"},

			#ebuilds to test mask and keyword changes
			"app-text/A-1": {},
			"app-text/B-1": { "KEYWORDS": "~x86" },
			"app-text/C-1": { "KEYWORDS": "" },
			"app-text/D-1": { "KEYWORDS": "~x86" },
			"app-text/D-2": { "KEYWORDS": "" },

			#ebuilds for mixed test for || dep handling
			"sci-libs/K-1": { "DEPEND": " || ( sci-libs/L[bar] || ( sci-libs/M sci-libs/P ) )", "EAPI": 2},
			"sci-libs/K-2": { "DEPEND": " || ( sci-libs/L[bar] || ( sci-libs/P sci-libs/M ) )", "EAPI": 2},
			"sci-libs/K-3": { "DEPEND": " || ( sci-libs/M || ( sci-libs/L[bar] sci-libs/P ) )", "EAPI": 2},
			"sci-libs/K-4": { "DEPEND": " || ( sci-libs/M || ( sci-libs/P sci-libs/L[bar] ) )", "EAPI": 2},
			"sci-libs/K-5": { "DEPEND": " || ( sci-libs/P || ( sci-libs/L[bar] sci-libs/M ) )", "EAPI": 2},
			"sci-libs/K-6": { "DEPEND": " || ( sci-libs/P || ( sci-libs/M sci-libs/L[bar] ) )", "EAPI": 2},
			"sci-libs/K-7": { "DEPEND": " || ( sci-libs/M sci-libs/L[bar] )", "EAPI": 2},
			"sci-libs/K-8": { "DEPEND": " || ( sci-libs/L[bar] sci-libs/M )", "EAPI": 2},

			"sci-libs/L-1": { "IUSE": "bar" },
			"sci-libs/M-1": { "KEYWORDS": "~x86" },
			"sci-libs/P-1": { },

			#ebuilds to test these nice "required by cat/pkg[foo]" messages
			"dev-util/Q-1": { "DEPEND": "foo? ( dev-util/R[bar] )", "IUSE": "+foo", "EAPI": 2 },
			"dev-util/Q-2": { "RDEPEND": "!foo? ( dev-util/R[bar] )", "IUSE": "foo", "EAPI": 2 },
			"dev-util/R-1": { "IUSE": "bar" },

			#ebuilds to test interaction with REQUIRED_USE
			"app-portage/A-1": { "DEPEND": "app-portage/B[foo]", "EAPI": 2 },
			"app-portage/A-2": { "DEPEND": "app-portage/B[foo=]", "IUSE": "+foo", "REQUIRED_USE": "foo", "EAPI": "4" },

			"app-portage/B-1": { "IUSE": "foo +bar", "REQUIRED_USE": "^^ ( foo bar )", "EAPI": "4" },
			"app-portage/C-1": { "IUSE": "+foo +bar", "REQUIRED_USE": "^^ ( foo bar )", "EAPI": "4" },

			"sci-mathematics/octave-4.2.2": {
				"EAPI": 6,
				"RDEPEND": ">=x11-libs/qscintilla-2.9.3-r2:=[qt5(+)]",
			},
			"x11-libs/qscintilla-2.9.4": {
				"EAPI": 6,
				"IUSE": "+qt4 qt5",
				"REQUIRED_USE": "^^ ( qt4 qt5 )",
			},
			"x11-libs/qscintilla-2.10": {
				"EAPI": 6,
				"KEYWORDS": "~x86",
				"IUSE": "qt4 +qt5",
			},
			}

		test_cases = (
				#Test USE changes.
				#The simple case.

				ResolverPlaygroundTestCase(
					["dev-libs/A:1"],
					options={"--autounmask": "n"},
					success=False),
				ResolverPlaygroundTestCase(
					["dev-libs/A:1"],
					options={"--autounmask": True},
					success=False,
					mergelist=["dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1"],
					use_changes={ "dev-libs/B-1": {"foo": True} }),

				ResolverPlaygroundTestCase(
					["dev-libs/A:1"],
					options={"--autounmask-use": "y"},
					success=False,
					mergelist=["dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1"],
					use_changes={ "dev-libs/B-1": {"foo": True} }),

				# Test default --autounmask-use
				ResolverPlaygroundTestCase(
					["dev-libs/A:1"],
					success=False,
					mergelist=["dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1"],
					use_changes={ "dev-libs/B-1": {"foo": True} }),

				# Explicitly disable --autounmask-use
				ResolverPlaygroundTestCase(
					["dev-libs/A:1"],
					success=False,
					options={"--autounmask-use": "n"}),

				#Make sure we restart if needed.
				ResolverPlaygroundTestCase(
					["dev-libs/A:1", "dev-libs/B"],
					options={"--autounmask": True, "--autounmask-backtrack": "y"},
					all_permutations=True,
					success=False,
					mergelist=["dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1"],
					use_changes={ "dev-libs/B-1": {"foo": True} }),

				# With --autounmask-backtrack=y:
				#[ebuild  N     ] dev-libs/C-1
				#[ebuild  N     ] dev-libs/B-1  USE="foo -bar"
				#[ebuild  N     ] dev-libs/A-1
				#
				#The following USE changes are necessary to proceed:
				# (see "package.use" in the portage(5) man page for more details)
				## required by dev-libs/A-1::test_repo
				## required by dev-libs/A:1 (argument)
				#>=dev-libs/B-1 foo

				# Without --autounmask-backtrack=y:
				#[ebuild  N     ] dev-libs/B-1  USE="foo -bar"
				#[ebuild  N     ] dev-libs/A-1
				#
				#The following USE changes are necessary to proceed:
				# (see "package.use" in the portage(5) man page for more details)
				## required by dev-libs/A-1::test_repo
				## required by dev-libs/A:1 (argument)
				#>=dev-libs/B-1 foo

				ResolverPlaygroundTestCase(
					["dev-libs/A:1", "dev-libs/A:2", "dev-libs/B"],
					options={"--autounmask": True, "--autounmask-backtrack": "y"},
					all_permutations=True,
					success=False,
					mergelist=["dev-libs/D-1", "dev-libs/C-1", "dev-libs/B-1", "dev-libs/A-1", "dev-libs/A-2"],
					ignore_mergelist_order=True,
					use_changes={ "dev-libs/B-1": {"foo": True, "bar": True} }),

				# With --autounmask-backtrack=y:
				#[ebuild  N     ] dev-libs/C-1
				#[ebuild  N     ] dev-libs/D-1
				#[ebuild  N     ] dev-libs/B-1  USE="bar foo"
				#[ebuild  N     ] dev-libs/A-2
				#[ebuild  N     ] dev-libs/A-1
				#
				#The following USE changes are necessary to proceed:
				# (see "package.use" in the portage(5) man page for more details)
				## required by dev-libs/A-2::test_repo
				## required by dev-libs/A:2 (argument)
				#>=dev-libs/B-1 bar foo

				# Without --autounmask-backtrack=y:
				#[ebuild  N     ] dev-libs/B-1  USE="bar foo"
				#[ebuild  N     ] dev-libs/A-1
				#[ebuild  N     ] dev-libs/A-2
				#
				#The following USE changes are necessary to proceed:
				# (see "package.use" in the portage(5) man page for more details)
				## required by dev-libs/A-1::test_repo
				## required by dev-libs/A:1 (argument)
				#>=dev-libs/B-1 foo bar

				# NOTE: The --autounmask-backtrack=n behavior is acceptable, but
				# it would be nicer if it added the dev-libs/C-1 and dev-libs/D-1
				# deps to the depgraph without backtracking. It could add two
				# instances of dev-libs/B-1 to the graph with different USE flags,
				# and then use _solve_non_slot_operator_slot_conflicts to eliminate
				# the redundant instance.

				#Test keywording.
				#The simple case.

				ResolverPlaygroundTestCase(
					["app-misc/Z"],
					options={"--autounmask": "n"},
					success=False),
				ResolverPlaygroundTestCase(
					["app-misc/Z"],
					options={"--autounmask": True},
					success=False,
					mergelist=["app-misc/Y-1", "app-misc/Z-1"],
					unstable_keywords=["app-misc/Y-1", "app-misc/Z-1"]),

				#Make sure that the backtracking for slot conflicts handles our mess.

				ResolverPlaygroundTestCase(
					["=app-misc/V-1", "app-misc/W"],
					options={"--autounmask": True},
					all_permutations=True,
					success=False,
					mergelist=["app-misc/W-2", "app-misc/V-1"],
					unstable_keywords=["app-misc/W-2", "app-misc/V-1"]),

				#Mixed testing
				#Make sure we don't change use for something in a || dep if there is another choice
				#that needs no change.

				ResolverPlaygroundTestCase(
					["=sci-libs/K-1"],
					options={"--autounmask": True},
					success=True,
					mergelist=["sci-libs/P-1", "sci-libs/K-1"]),
				ResolverPlaygroundTestCase(
					["=sci-libs/K-2"],
					options={"--autounmask": True},
					success=True,
					mergelist=["sci-libs/P-1", "sci-libs/K-2"]),
				ResolverPlaygroundTestCase(
					["=sci-libs/K-3"],
					options={"--autounmask": True},
					success=True,
					mergelist=["sci-libs/P-1", "sci-libs/K-3"]),
				ResolverPlaygroundTestCase(
					["=sci-libs/K-4"],
					options={"--autounmask": True},
					success=True,
					mergelist=["sci-libs/P-1", "sci-libs/K-4"]),
				ResolverPlaygroundTestCase(
					["=sci-libs/K-5"],
					options={"--autounmask": True},
					success=True,
					mergelist=["sci-libs/P-1", "sci-libs/K-5"]),
				ResolverPlaygroundTestCase(
					["=sci-libs/K-6"],
					options={"--autounmask": True},
					success=True,
					mergelist=["sci-libs/P-1", "sci-libs/K-6"]),

				#Make sure we prefer use changes over keyword changes.
				ResolverPlaygroundTestCase(
					["=sci-libs/K-7"],
					options={"--autounmask": True},
					success=False,
					mergelist=["sci-libs/L-1", "sci-libs/K-7"],
					use_changes={ "sci-libs/L-1": { "bar": True } }),
				ResolverPlaygroundTestCase(
					["=sci-libs/K-8"],
					options={"--autounmask": True},
					success=False,
					mergelist=["sci-libs/L-1", "sci-libs/K-8"],
					use_changes={ "sci-libs/L-1": { "bar": True } }),

				#Test these nice "required by cat/pkg[foo]" messages.
				ResolverPlaygroundTestCase(
					["=dev-util/Q-1"],
					options={"--autounmask": True},
					success=False,
					mergelist=["dev-util/R-1", "dev-util/Q-1"],
					use_changes={ "dev-util/R-1": { "bar": True } }),
				ResolverPlaygroundTestCase(
					["=dev-util/Q-2"],
					options={"--autounmask": True},
					success=False,
					mergelist=["dev-util/R-1", "dev-util/Q-2"],
					use_changes={ "dev-util/R-1": { "bar": True } }),

				#Test interaction with REQUIRED_USE.
				# Some of these cases trigger USE change(s) that violate
				# REQUIRED_USE, so the USE changes are shown along with
				# the REQUIRED_USE violation that they would trigger.

				# The following USE changes are necessary to proceed:
				#  (see "package.use" in the portage(5) man page for more details)
				# # required by app-portage/A-1::test_repo
				# # required by =app-portage/A-1 (argument)
				# >=app-portage/B-1 foo
				#
				# !!! The ebuild selected to satisfy "app-portage/B[foo]" has unmet requirements.
				# - app-portage/B-1::test_repo USE="bar (forced-flag) -foo"
				#
				#   The following REQUIRED_USE flag constraints are unsatisfied:
				#     exactly-one-of ( foo bar )
				ResolverPlaygroundTestCase(
					["=app-portage/A-1"],
					options={ "--autounmask": True },
					use_changes={"app-portage/B-1": {"foo": True}},
					success=False),

				# The following USE changes are necessary to proceed:
				#  (see "package.use" in the portage(5) man page for more details)
				# # required by app-portage/A-2::test_repo
				# # required by =app-portage/A-2 (argument)
				# >=app-portage/B-1 foo
				#
				# !!! The ebuild selected to satisfy "app-portage/B[foo=]" has unmet requirements.
				# - app-portage/B-1::test_repo USE="bar (forced-flag) -foo"
				#
				#   The following REQUIRED_USE flag constraints are unsatisfied:
				#     exactly-one-of ( foo bar )
				ResolverPlaygroundTestCase(
					["=app-portage/A-2"],
					options={ "--autounmask": True },
					use_changes={"app-portage/B-1": {"foo": True}},
					success=False),
				ResolverPlaygroundTestCase(
					["=app-portage/C-1"],
					options={ "--autounmask": True },
					use_changes=None,
					success=False),

				# Test bug 622462, where it inappropriately unmasked a newer
				# version rather than report unsatisfied REQUIRED_USE.
				#
				# The following USE changes are necessary to proceed:
				#  (see "package.use" in the portage(5) man page for more details)
				# # required by sci-mathematics/octave-4.2.2::test_repo
				# # required by sci-mathematics/octave (argument)
				# >=x11-libs/qscintilla-2.9.4 qt5
				#
				# !!! The ebuild selected to satisfy ">=x11-libs/qscintilla-2.9.3-r2:=[qt5(+)]" has unmet requirements.
				# - x11-libs/qscintilla-2.9.4::test_repo USE="qt4 -qt5"
				#
				#   The following REQUIRED_USE flag constraints are unsatisfied:
				#     exactly-one-of ( qt4 qt5 )
				#
				# (dependency required by "sci-mathematics/octave-4.2.2::test_repo" [ebuild])
				# (dependency required by "sci-mathematics/octave" [argument])
				ResolverPlaygroundTestCase(
					["sci-mathematics/octave"],
					options={"--autounmask": True},
					use_changes={"x11-libs/qscintilla-2.9.4": {"qt5": True}},
					success=False),

				#Make sure we don't change masked/forced flags.
				ResolverPlaygroundTestCase(
					["dev-libs/E:1"],
					options={"--autounmask": True},
					use_changes=None,
					success=False),
				ResolverPlaygroundTestCase(
					["dev-libs/E:2"],
					options={"--autounmask": True},
					use_changes=None,
					success=False),

				#Test mask and keyword changes.
				ResolverPlaygroundTestCase(
					["app-text/A"],
					options={"--autounmask": True},
					success=False,
					mergelist=["app-text/A-1"],
					needed_p_mask_changes=["app-text/A-1"]),
				ResolverPlaygroundTestCase(
					["app-text/B"],
					options={"--autounmask": True},
					success=False,
					mergelist=["app-text/B-1"],
					unstable_keywords=["app-text/B-1"],
					needed_p_mask_changes=["app-text/B-1"]),
				ResolverPlaygroundTestCase(
					["app-text/C"],
					options={"--autounmask": True},
					success=False,
					mergelist=["app-text/C-1"],
					unstable_keywords=["app-text/C-1"],
					needed_p_mask_changes=["app-text/C-1"]),
				#Make sure unstable keyword is preferred over missing keyword
				ResolverPlaygroundTestCase(
					["app-text/D"],
					options={"--autounmask": True},
					success=False,
					mergelist=["app-text/D-1"],
					unstable_keywords=["app-text/D-1"]),
				#Test missing keyword
				ResolverPlaygroundTestCase(
					["=app-text/D-2"],
					options={"--autounmask": True},
					success=False,
					mergelist=["app-text/D-2"],
					unstable_keywords=["app-text/D-2"])
			)

		profile = {
			"use.mask":
				(
					"masked-flag",
				),
			"use.force":
				(
					"forced-flag",
				),
			"package.mask":
				(
					"app-text/A",
					"app-text/B",
					"app-text/C",
				),
		}

		playground = ResolverPlayground(ebuilds=ebuilds, profile=profile)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testAutounmaskForLicenses(self):

		ebuilds = {
			"dev-libs/A-1": { "LICENSE": "TEST" },
			"dev-libs/B-1": { "LICENSE": "TEST", "IUSE": "foo", "KEYWORDS": "~x86"},
			"dev-libs/C-1": { "DEPEND": "dev-libs/B[foo]", "EAPI": 2 },

			"dev-libs/D-1": { "DEPEND": "dev-libs/E dev-libs/F", "LICENSE": "TEST" },
			"dev-libs/E-1": { "LICENSE": "TEST" },
			"dev-libs/E-2": { "LICENSE": "TEST" },
			"dev-libs/F-1": { "DEPEND": "=dev-libs/E-1", "LICENSE": "TEST" },

			"dev-java/sun-jdk-1.6.0.32": { "LICENSE": "TEST", "KEYWORDS": "~x86" },
			"dev-java/sun-jdk-1.6.0.31": { "LICENSE": "TEST", "KEYWORDS": "x86" },
			}

		test_cases = (
				# --autounmask=n negates default --autounmask-license
				ResolverPlaygroundTestCase(
					["=dev-libs/A-1"],
					options={"--autounmask": 'n'},
					success=False),
				ResolverPlaygroundTestCase(
					["=dev-libs/A-1"],
					options={"--autounmask-license": "y"},
					success=False,
					mergelist=["dev-libs/A-1"],
					license_changes={ "dev-libs/A-1": set(["TEST"]) }),

				# Test that --autounmask enables --autounmask-license
				ResolverPlaygroundTestCase(
					["=dev-libs/A-1"],
					options={"--autounmask": True},
					success=False,
					mergelist=["dev-libs/A-1"],
					license_changes={ "dev-libs/A-1": set(["TEST"]) }),

				# Test that --autounmask-license is not enabled by default
				ResolverPlaygroundTestCase(
					["=dev-libs/A-1"],
					success=False,
				),

				# Test that --autounmask does not override --autounmask-license=n
				ResolverPlaygroundTestCase(
					["=dev-libs/A-1"],
					options={"--autounmask": True, "--autounmask-license": "n"},
					success=False,
				),

				# Test that --autounmask=n overrides --autounmask-license=y
				ResolverPlaygroundTestCase(
					["=dev-libs/A-1"],
					options={"--autounmask": "n", "--autounmask-license": "y"},
					success=False,
				),

				ResolverPlaygroundTestCase(
					["=dev-libs/A-1"],
					options={"--autounmask-license": "n"},
					success=False),

				#Test license+keyword+use change at once.
				ResolverPlaygroundTestCase(
					["=dev-libs/C-1"],
					options={"--autounmask": True},
					success=False,
					mergelist=["dev-libs/B-1", "dev-libs/C-1"],
					license_changes={ "dev-libs/B-1": set(["TEST"]) },
					unstable_keywords=["dev-libs/B-1"],
					use_changes={ "dev-libs/B-1": { "foo": True } }),

				#Test license with backtracking.
				ResolverPlaygroundTestCase(
					["=dev-libs/D-1"],
					options={"--autounmask": True},
					success=False,
					mergelist=["dev-libs/E-1", "dev-libs/F-1", "dev-libs/D-1"],
					license_changes={ "dev-libs/D-1": set(["TEST"]), "dev-libs/E-1": set(["TEST"]), "dev-libs/E-2": set(["TEST"]), "dev-libs/F-1": set(["TEST"]) }),

				#Test license only for bug #420847
				ResolverPlaygroundTestCase(
					["dev-java/sun-jdk"],
					options={"--autounmask": True},
					success=False,
					mergelist=["dev-java/sun-jdk-1.6.0.31"],
					license_changes={ "dev-java/sun-jdk-1.6.0.31": set(["TEST"]) }),
			)

		playground = ResolverPlayground(ebuilds=ebuilds)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testAutounmaskAndSets(self):

		ebuilds = {
			#ebuilds to test use changes
			"dev-libs/A-1": { },
			"dev-libs/A-2": { "KEYWORDS": "~x86" },
			"dev-libs/B-1": { "DEPEND": "dev-libs/A" },
			"dev-libs/C-1": { "DEPEND": ">=dev-libs/A-2" },
			"dev-libs/D-1": { "DEPEND": "dev-libs/A" },
			}

		world_sets = ["@test-set"]
		sets = {
			"test-set": (
					"dev-libs/A", "dev-libs/B", "dev-libs/C", "dev-libs/D",
				),
			}

		test_cases = (
				#Test USE changes.
				#The simple case.

				ResolverPlaygroundTestCase(
					["dev-libs/B", "dev-libs/C", "dev-libs/D"],
					all_permutations=True,
					options={"--autounmask": "y"},
					mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
					ignore_mergelist_order=True,
					unstable_keywords=["dev-libs/A-2"],
					success=False),

				ResolverPlaygroundTestCase(
					["@test-set"],
					all_permutations=True,
					options={"--autounmask": "y"},
					mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
					ignore_mergelist_order=True,
					unstable_keywords=["dev-libs/A-2"],
					success=False),

				ResolverPlaygroundTestCase(
					["@world"],
					all_permutations=True,
					options={"--autounmask": "y"},
					mergelist=["dev-libs/A-2", "dev-libs/B-1", "dev-libs/C-1", "dev-libs/D-1"],
					ignore_mergelist_order=True,
					unstable_keywords=["dev-libs/A-2"],
					success=False),
			)


		playground = ResolverPlayground(ebuilds=ebuilds, world_sets=world_sets, sets=sets)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testAutounmaskKeepMasks(self):
		"""
		Ensure that we try to use a masked version with keywords before trying
		masked version with missing keywords (prefer masked regular version
		over -9999 version).
		"""
		ebuilds = {
			"app-text/A-1": {},
			}

		test_cases = (
				#Test mask and keyword changes.
				ResolverPlaygroundTestCase(
					["app-text/A"],
					options={"--autounmask": True,
							"--autounmask-keep-masks": "y"},
					success=False),
				ResolverPlaygroundTestCase(
					["app-text/A"],
					options={"--autounmask": True,
							"--autounmask-keep-masks": "n"},
					success=False,
					mergelist=["app-text/A-1"],
					needed_p_mask_changes=["app-text/A-1"]),
			)

		profile = {
			"package.mask":
				(
					"app-text/A",
				),
		}

		playground = ResolverPlayground(ebuilds=ebuilds, profile=profile)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testAutounmask9999(self):

		ebuilds = {
			"dev-libs/A-1": { },
			"dev-libs/A-2": { },
			"dev-libs/A-9999": { "KEYWORDS": "" },
			"dev-libs/B-1": { "DEPEND": ">=dev-libs/A-2" },
			"dev-libs/C-1": { "DEPEND": ">=dev-libs/A-3" },
			}

		profile = {
			"package.mask":
				(
					">=dev-libs/A-2",
				),
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				success=False,
				options={"--autounmask": True},
				mergelist=["dev-libs/A-2", "dev-libs/B-1"],
				needed_p_mask_changes=set(["dev-libs/A-2"])),

			ResolverPlaygroundTestCase(
				["dev-libs/C"],
				success=False,
				options={"--autounmask": True},
				mergelist=["dev-libs/A-9999", "dev-libs/C-1"],
				unstable_keywords=set(["dev-libs/A-9999"]),
				needed_p_mask_changes=set(["dev-libs/A-9999"])),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, profile=profile)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
