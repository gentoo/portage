# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class FeaturesTestUse(TestCase):

	def testFeaturesTestUse(self):
		ebuilds = {
			"dev-libs/A-1" : {
				"IUSE": "test"
			},
			"dev-libs/B-1" : {
				"IUSE": "test foo"
			},
		}

		installed = {
			"dev-libs/A-1" : {
				"USE": "",
				"IUSE": "test"
			},
			"dev-libs/B-1" : {
				"USE": "foo",
				"IUSE": "test foo"
			},
		}

		user_config = {
			"make.conf" : ("FEATURES=test", "USE=\"-test -foo\"")
		}

		test_cases = (

			# USE=test state should not trigger --newuse rebuilds, as
			# specified in bug #373209, comment #3.
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--newuse": True, "--selective": True},
				success = True,
				mergelist = []),

			# USE=-test -> USE=test, with USE=test forced by FEATURES=test
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {},
				success = True,
				mergelist = ["dev-libs/A-1"]),

			# USE=foo -> USE=-foo, with USE=test forced by FEATURES=test
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				options = {"--newuse": True, "--selective": True},
				success = True,
				mergelist = ["dev-libs/B-1"]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, user_config=user_config, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

