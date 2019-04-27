# Copyright 2012-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotAbiDowngradeTestCase(TestCase):

	def __init__(self, *args, **kwargs):
		super(SlotAbiDowngradeTestCase, self).__init__(*args, **kwargs)

	def testSubSlot(self):
		ebuilds = {
			"dev-libs/icu-4.8" : {
				"EAPI": "5",
				"SLOT": "0/48"
			},
			"dev-libs/libxml2-2.7.8" : {
				"EAPI": "5",
				"DEPEND":  "dev-libs/icu:=",
				"RDEPEND": "dev-libs/icu:="
			},
		}
		binpkgs = {
			"dev-libs/icu-49" : {
				"EAPI": "5",
				"SLOT": "0/49"
			},
			"dev-libs/icu-4.8" : {
				"EAPI": "5",
				"SLOT": "0/48"
			},
			"dev-libs/libxml2-2.7.8" : {
				"EAPI": "5",
				"DEPEND":  "dev-libs/icu:0/49=",
				"RDEPEND": "dev-libs/icu:0/49="
			},
		}
		installed = {
			"dev-libs/icu-49" : {
				"EAPI": "5",
				"SLOT": "0/49"
			},
			"dev-libs/libxml2-2.7.8" : {
				"EAPI": "5",
				"DEPEND":  "dev-libs/icu:0/49=",
				"RDEPEND": "dev-libs/icu:0/49="
			},
		}

		world = ["dev-libs/libxml2"]

		test_cases = (

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {"--oneshot": True},
				success = True,
				mergelist = ["dev-libs/icu-4.8", "dev-libs/libxml2-2.7.8" ]),

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {"--oneshot": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["dev-libs/icu-4.8"]),

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {"--oneshot": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/icu-4.8", "dev-libs/libxml2-2.7.8" ]),

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {"--oneshot": True, "--usepkgonly": True},
				success = True,
				mergelist = ["[binary]dev-libs/icu-49"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["dev-libs/icu-4.8", "dev-libs/libxml2-2.7.8" ]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["dev-libs/icu-4.8"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/icu-4.8", "dev-libs/libxml2-2.7.8" ]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkgonly": True},
				success = True,
				mergelist = []),

		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testWholeSlotSubSlotMix(self):
		ebuilds = {
			"dev-libs/glib-1.2.10" : {
				"SLOT": "1"
			},
			"dev-libs/glib-2.30.2" : {
				"EAPI": "5",
				"SLOT": "2/2.30"
			},
			"dev-libs/dbus-glib-0.98" : {
				"EAPI": "5",
				"DEPEND":  "dev-libs/glib:2=",
				"RDEPEND": "dev-libs/glib:2="
			},
		}
		binpkgs = {
			"dev-libs/glib-1.2.10" : {
				"SLOT": "1"
			},
			"dev-libs/glib-2.30.2" : {
				"EAPI": "5",
				"SLOT": "2/2.30"
			},
			"dev-libs/glib-2.32.3" : {
				"EAPI": "5",
				"SLOT": "2/2.32"
			},
			"dev-libs/dbus-glib-0.98" : {
				"EAPI": "5",
				"DEPEND":  "dev-libs/glib:2/2.32=",
				"RDEPEND": "dev-libs/glib:2/2.32="
			},
		}
		installed = {
			"dev-libs/glib-1.2.10" : {
				"EAPI": "5",
				"SLOT": "1"
			},
			"dev-libs/glib-2.32.3" : {
				"EAPI": "5",
				"SLOT": "2/2.32"
			},
			"dev-libs/dbus-glib-0.98" : {
				"EAPI": "5",
				"DEPEND":  "dev-libs/glib:2/2.32=",
				"RDEPEND": "dev-libs/glib:2/2.32="
			},
		}

		world = ["dev-libs/glib:1", "dev-libs/dbus-glib"]

		test_cases = (

			ResolverPlaygroundTestCase(
				["dev-libs/glib"],
				options = {"--oneshot": True},
				success = True,
				mergelist = ["dev-libs/glib-2.30.2", "dev-libs/dbus-glib-0.98" ]),

			ResolverPlaygroundTestCase(
				["dev-libs/glib"],
				options = {"--oneshot": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["dev-libs/glib-2.30.2"]),

			ResolverPlaygroundTestCase(
				["dev-libs/glib"],
				options = {"--oneshot": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/glib-2.30.2", "dev-libs/dbus-glib-0.98" ]),

			ResolverPlaygroundTestCase(
				["dev-libs/glib"],
				options = {"--oneshot": True, "--usepkgonly": True},
				success = True,
				mergelist = ["[binary]dev-libs/glib-2.32.3"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["dev-libs/glib-2.30.2", "dev-libs/dbus-glib-0.98" ]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["dev-libs/glib-2.30.2"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/glib-2.30.2", "dev-libs/dbus-glib-0.98" ]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkgonly": True},
				success = True,
				mergelist = []),

		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
