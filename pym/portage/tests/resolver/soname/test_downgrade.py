# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SonameDowngradeTestCase(TestCase):

	def testSingleSlot(self):

		ebuilds = {
			"dev-libs/icu-49" : {
			},
			"dev-libs/icu-4.8" : {
			},
			"dev-libs/libxml2-2.7.8" : {
				"DEPEND": "dev-libs/icu",
				"RDEPEND": "dev-libs/icu",
			},
		}

		binpkgs = {
			"dev-libs/icu-49" : {
				"PROVIDES": "x86_32: libicu.so.49",
			},
			"dev-libs/icu-4.8" : {
				"PROVIDES": "x86_32: libicu.so.48",
			},
			"dev-libs/libxml2-2.7.8" : {
				"DEPEND": "dev-libs/icu",
				"RDEPEND": "dev-libs/icu",
				"REQUIRES": "x86_32: libicu.so.48",
			},
		}
		installed = {
			"dev-libs/icu-49" : {
				"PROVIDES": "x86_32: libicu.so.49",
			},
			"dev-libs/libxml2-2.7.8" : {
				"DEPEND": "dev-libs/icu",
				"RDEPEND": "dev-libs/icu",
				"REQUIRES": "x86_32: libicu.so.49",
			},
		}

		user_config = {
			"package.mask" : (
				">=dev-libs/icu-49",
			),
		}

		world = ["dev-libs/libxml2"]

		test_cases = (

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {
					"--autounmask": "n",
					"--ignore-soname-deps": "n",
					"--oneshot": True,
					"--usepkgonly": True
				},
				success = True,
				mergelist = [
					"[binary]dev-libs/icu-4.8",
					"[binary]dev-libs/libxml2-2.7.8"
				]
			),

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {
					"--autounmask": "n",
					"--ignore-soname-deps": "y",
					"--oneshot": True,
					"--usepkgonly": True
				},
				success = True,
				mergelist = [
					"[binary]dev-libs/icu-4.8",
				]
			),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--autounmask": "n",
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					"[binary]dev-libs/icu-4.8",
					"[binary]dev-libs/libxml2-2.7.8"
				]
			),

			# In this case, soname dependencies are not respected,
			# because --usepkgonly is not enabled. This could be
			# handled differently, by respecting soname dependencies
			# as long as no unbuilt ebuilds get pulled into the graph.
			# However, that kind of conditional dependency accounting
			# would add a significant amount of complexity.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkg": True,
				},
				success = True,
				mergelist = [
					"[binary]dev-libs/icu-4.8",
				]
			),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--deep": True,
					"--update": True,
				},
				success = True,
				mergelist = [
					"dev-libs/icu-4.8",
				]
			),
		)

		playground = ResolverPlayground(binpkgs=binpkgs,
			ebuilds=ebuilds, installed=installed,
			user_config=user_config, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			playground.debug = False
			playground.cleanup()

	def testTwoSlots(self):

		ebuilds = {
			"dev-libs/glib-1.2.10" : {
				"SLOT": "1"
			},
			"dev-libs/glib-2.30.2" : {
				"SLOT": "2"
			},
			"dev-libs/dbus-glib-0.98" : {
				"EAPI": "1",
				"DEPEND":  "dev-libs/glib:2",
				"RDEPEND": "dev-libs/glib:2"
			},
		}
		binpkgs = {
			"dev-libs/glib-1.2.10" : {
				"SLOT": "1",
				"PROVIDES": "x86_32: libglib-1.0.so.0",
			},
			"dev-libs/glib-2.30.2" : {
				"PROVIDES": "x86_32: libglib-2.0.so.30",
				"SLOT": "2",
			},
			"dev-libs/glib-2.32.3" : {
				"PROVIDES": "x86_32: libglib-2.0.so.32",
				"SLOT": "2",
			},
			"dev-libs/dbus-glib-0.98" : {
				"EAPI": "1",
				"DEPEND":  "dev-libs/glib:2",
				"RDEPEND": "dev-libs/glib:2",
				"REQUIRES": "x86_32: libglib-2.0.so.30",
			},
		}
		installed = {
			"dev-libs/glib-1.2.10" : {
				"PROVIDES": "x86_32: libglib-1.0.so.0",
				"SLOT": "1",
			},
			"dev-libs/glib-2.32.3" : {
				"PROVIDES": "x86_32: libglib-2.0.so.32",
				"SLOT": "2",
			},
			"dev-libs/dbus-glib-0.98" : {
				"EAPI": "1",
				"DEPEND":  "dev-libs/glib:2",
				"RDEPEND": "dev-libs/glib:2",
				"REQUIRES": "x86_32: libglib-2.0.so.32",
			},
		}

		user_config = {
			"package.mask" : (
				">=dev-libs/glib-2.32",
			),
		}

		world = [
			"dev-libs/glib:1",
			"dev-libs/dbus-glib",
		]

		test_cases = (

			ResolverPlaygroundTestCase(
				["@world"],
				options = {
					"--autounmask": "n",
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True,
				},
				success = True,
				mergelist = [
					"[binary]dev-libs/glib-2.30.2",
					"[binary]dev-libs/dbus-glib-0.98"
				]
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, user_config=user_config, world=world,
			debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			playground.debug = False
			playground.cleanup()
