# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground, ResolverPlaygroundTestCase)

class SonameAutoUnmaskTestCase(TestCase):

	def testSonameAutoUnmask(self):

		binpkgs = {
			"dev-libs/icu-49" : {
				"KEYWORDS": "x86",
				"PROVIDES": "x86_32: libicu.so.49",
			},
			"dev-libs/icu-4.8" : {
				"KEYWORDS": "x86",
				"PROVIDES": "x86_32: libicu.so.48",
			},
			"dev-libs/libxml2-2.7.8" : {
				"KEYWORDS": "~x86",
				"DEPEND":  "dev-libs/icu",
				"RDEPEND": "dev-libs/icu",
				"REQUIRES": "x86_32: libicu.so.49",
			},
		}

		installed = {
			"dev-libs/icu-4.8" : {
				"KEYWORDS": "x86",
				"PROVIDES": "x86_32: libicu.so.48",
			},
			"dev-libs/libxml2-2.7.8" : {
				"KEYWORDS": "~x86",
				"DEPEND":  "dev-libs/icu",
				"RDEPEND": "dev-libs/icu",
				"REQUIRES": "x86_32: libicu.so.48",
			},
		}

		world = ["dev-libs/libxml2"]

		test_cases = (

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {
					"--autounmask": True,
					"--ignore-soname-deps": "n",
					"--oneshot": True,
					"--usepkgonly": True,
				},
				success = False,
				mergelist = [
					"[binary]dev-libs/icu-49",
					"[binary]dev-libs/libxml2-2.7.8"
				],
				unstable_keywords = ['dev-libs/libxml2-2.7.8'],
			),

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {
					"--autounmask": True,
					"--ignore-soname-deps": "y",
					"--oneshot": True,
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					"[binary]dev-libs/icu-49"
				]
			),

			# Test that dev-libs/icu-49 update is skipped due to
			# dev-libs/libxml2-2.7.8 being masked by KEYWORDS. Note
			# that this result is questionable, since the installed
			# dev-libs/libxml2-2.7.8 instance is also masked!
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--autounmask": True,
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [],
			),

		)

		playground = ResolverPlayground(binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.debug = False
			playground.cleanup()
