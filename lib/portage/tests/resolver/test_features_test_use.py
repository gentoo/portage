# Copyright 2012-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)


class TestDepend(TestCase):
	ebuilds = {
		"dev-libs/A-1" : {
			"IUSE": "test",
			"DEPEND": "test? ( dev-libs/B )",
		},
		"dev-libs/B-1" : {
		},
	}

	installed = {
		"dev-libs/A-1" : {
			"USE": "",
			"IUSE": "test",
			"DEPEND": "test? ( dev-libs/B )",
		},
	}

	def test_default_use_test(self):
		"""
		Test that FEATURES=test enables USE=test by default.
		"""
		user_config = {
			"make.conf" : ("FEATURES=test", "USE=\"\"")
		}
		test_case = ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {},
				success = True,
				mergelist = ["dev-libs/B-1", "dev-libs/A-1"])

		playground = ResolverPlayground(ebuilds=self.ebuilds,
			user_config=user_config, debug=False)
		try:
			playground.run_TestCase(test_case)
			self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def test_no_forced_use_test(self):
		"""
		Test that FEATURES=test no longer forces USE=test.
		"""
		user_config = {
			"make.conf" : ("FEATURES=test", "USE=\"-test\"")
		}
		test_case = ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {},
				success = True,
				mergelist = ["dev-libs/A-1"])

		playground = ResolverPlayground(ebuilds=self.ebuilds,
			user_config=user_config, debug=False)
		try:
			playground.run_TestCase(test_case)
			self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def test_newuse(self):
		"""
		Test that --newuse now detects USE=test changes.
		"""
		user_config = {
			"make.conf" : ("FEATURES=test", "USE=\"\"")
		}
		test_case = ResolverPlaygroundTestCase(
				["dev-libs/A"],
				options = {"--newuse": True, "--selective": True},
				success = True,
				mergelist = ["dev-libs/B-1", "dev-libs/A-1"])

		playground = ResolverPlayground(ebuilds=self.ebuilds,
			user_config=user_config, debug=False)
		try:
			playground.run_TestCase(test_case)
			self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
