# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class SimpleResolverTestCase(TestCase):

	def testSimple(self):
		ebuilds = {
			"dev-libs/A-1": { "KEYWORDS": "x86" },
			"dev-libs/A-2": { "KEYWORDS": "~x86" },
			"dev-libs/B-1.2": {},

			"app-misc/Z-1": { "DEPEND": "|| ( app-misc/Y ( app-misc/X app-misc/W ) )", "RDEPEND": "" },
			"app-misc/Y-1": { "KEYWORDS": "~x86" },
			"app-misc/X-1": {},
			"app-misc/W-1": {},
			}
		binpkgs = {
			"dev-libs/B-1.2": {},
		}
		installed = {
			"dev-libs/A-1": {},
			"dev-libs/B-1.1": {},
			}

		test_cases = (
			ResolverPlaygroundTestCase(["dev-libs/A"], success = True, mergelist = ["dev-libs/A-1"]),
			ResolverPlaygroundTestCase(["=dev-libs/A-2"], options = { "--autounmask": 'n' }, success = False),

			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--noreplace": True},
				success = True,
				mergelist = []),
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options = {"--noreplace": True},
				success = True,
				mergelist = []),
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options = {"--update": True},
				success = True,
				mergelist = ["dev-libs/B-1.2"]),

			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options = {"--update": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/B-1.2"]),

			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options = {"--update": True, "--usepkgonly": True},
				success = True,
				mergelist = ["[binary]dev-libs/B-1.2"]),

			ResolverPlaygroundTestCase(
				["app-misc/Z"],
				success = True,
				ambiguous_merge_order = True,
				mergelist = [("app-misc/W-1", "app-misc/X-1"), "app-misc/Z-1"]),
			)

		playground = ResolverPlayground(ebuilds=ebuilds,
			binpkgs=binpkgs, installed=installed)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
