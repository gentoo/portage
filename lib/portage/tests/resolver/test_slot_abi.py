# Copyright 2012-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SlotAbiTestCase(TestCase):

	def __init__(self, *args, **kwargs):
		super(SlotAbiTestCase, self).__init__(*args, **kwargs)

	def testSubSlot(self):
		ebuilds = {
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
				"DEPEND":  "dev-libs/icu:0/48=",
				"RDEPEND": "dev-libs/icu:0/48="
			},
		}
		installed = {
			"dev-libs/icu-4.8" : {
				"EAPI": "5",
				"SLOT": "0/48"
			},
			"dev-libs/libxml2-2.7.8" : {
				"EAPI": "5",
				"DEPEND":  "dev-libs/icu:0/48=",
				"RDEPEND": "dev-libs/icu:0/48="
			},
		}

		world = ["dev-libs/libxml2"]

		test_cases = (

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {"--oneshot": True},
				success = True,
				mergelist = ["dev-libs/icu-49", "dev-libs/libxml2-2.7.8" ]),

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {"--oneshot": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["dev-libs/icu-49"]),

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {"--oneshot": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/icu-49", "dev-libs/libxml2-2.7.8" ]),

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {"--oneshot": True, "--usepkgonly": True},
				success = True,
				mergelist = ["[binary]dev-libs/icu-4.8"]),

			ResolverPlaygroundTestCase(
				["dev-libs/icu"],
				options = {"--oneshot": True, "--usepkgonly": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["[binary]dev-libs/icu-49"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["dev-libs/icu-49", "dev-libs/libxml2-2.7.8" ]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["dev-libs/icu-49"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/icu-49", "dev-libs/libxml2-2.7.8" ]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkgonly": True},
				success = True,
				mergelist = []),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkgonly": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["[binary]dev-libs/icu-49"]),

		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testWholeSlot(self):
		ebuilds = {
			"sys-libs/db-4.8" : {
				"SLOT": "4.8"
			},
			"sys-libs/db-4.7" : {
				"SLOT": "4.7"
			},
			"app-office/libreoffice-3.5.4.2" : {
				"EAPI": "5",
				"DEPEND": ">=sys-libs/db-4:=",
				"RDEPEND": ">=sys-libs/db-4:="
			},
		}
		binpkgs = {
			"sys-libs/db-4.8" : {
				"SLOT": "4.8"
			},
			"sys-libs/db-4.7" : {
				"SLOT": "4.7"
			},
			"app-office/libreoffice-3.5.4.2" : {
				"EAPI": "5",
				"DEPEND":  ">=sys-libs/db-4:4.7/4.7=",
				"RDEPEND": ">=sys-libs/db-4:4.7/4.7="
			},
		}
		installed = {
			"sys-libs/db-4.7" : {
				"SLOT": "4.7"
			},
			"app-office/libreoffice-3.5.4.2" : {
				"EAPI": "5",
				"DEPEND":  ">=sys-libs/db-4:4.7/4.7=",
				"RDEPEND": ">=sys-libs/db-4:4.7/4.7="
			},
		}

		world = ["app-office/libreoffice"]

		test_cases = (

			# The first 2 test cases don't trigger a libreoffice rebuild
			# because sys-libs/db is the only package requested, and a
			# rebuild is not necessary because the sys-libs/db:4.7 slot
			# remains installed.
			ResolverPlaygroundTestCase(
				["sys-libs/db"],
				options = {"--oneshot": True},
				success = True,
				mergelist = ["sys-libs/db-4.8"]),

			ResolverPlaygroundTestCase(
				["sys-libs/db"],
				options = {"--oneshot": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]sys-libs/db-4.8"]),

			ResolverPlaygroundTestCase(
				["sys-libs/db"],
				options = {"--oneshot": True, "--usepkgonly": True},
				success = True,
				mergelist = ["[binary]sys-libs/db-4.8"]),

			ResolverPlaygroundTestCase(
				["sys-libs/db"],
				options = {"--oneshot": True, "--rebuild-if-new-slot": "n"},
				success = True,
				mergelist = ["sys-libs/db-4.8"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["sys-libs/db-4.8", "app-office/libreoffice-3.5.4.2"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]sys-libs/db-4.8", "app-office/libreoffice-3.5.4.2"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkg": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["[binary]sys-libs/db-4.8"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkgonly": True},
				success = True,
				mergelist = []),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkgonly": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["[binary]sys-libs/db-4.8"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--rebuild-if-new-slot": "n"},
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


	def testWholeSlotConditional(self):
		ebuilds = {
			"dev-libs/libnl-3.2.14" : {
				"SLOT": "3"
			},
			"dev-libs/libnl-1.1-r3" : {
				"SLOT": "1.1"
			},
			"net-misc/networkmanager-0.9.6.4-r1" : {
				"EAPI": "5",
				"IUSE": "wimax",
				"DEPEND": "wimax? ( dev-libs/libnl:1.1= ) !wimax? ( dev-libs/libnl:3= )",
				"RDEPEND": "wimax? ( dev-libs/libnl:1.1= ) !wimax? ( dev-libs/libnl:3= )"
			},
		}
		installed = {
			"dev-libs/libnl-1.1-r3" : {
				"SLOT": "1.1"
			},
			"net-misc/networkmanager-0.9.6.4-r1" : {
				"EAPI": "5",
				"IUSE": "wimax",
				"USE": "wimax",
				"DEPEND":  "dev-libs/libnl:1.1/1.1=",
				"RDEPEND": "dev-libs/libnl:1.1/1.1="
			},
		}

		user_config = {
			"make.conf" : ("USE=\"wimax\"",)
		}

		world = ["net-misc/networkmanager"]

		test_cases = (

			# Demonstrate bug #460304, where _slot_operator_update_probe needs
			# to account for USE conditional deps.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = []),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, user_config=user_config, world=world,
			debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

		user_config = {
			"make.conf" : ("USE=\"-wimax\"",)
		}

		test_cases = (

			# Demonstrate bug #460304 again, but with inverted USE
			# settings this time.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ['dev-libs/libnl-3.2.14', 'net-misc/networkmanager-0.9.6.4-r1']),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, user_config=user_config, world=world,
			debug=False)
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
			"dev-libs/glib-2.32.3" : {
				"EAPI": "5",
				"SLOT": "2/2.32"
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
				"DEPEND":  "dev-libs/glib:2/2.30=",
				"RDEPEND": "dev-libs/glib:2/2.30="
			},
		}
		installed = {
			"dev-libs/glib-1.2.10" : {
				"EAPI": "5",
				"SLOT": "1"
			},
			"dev-libs/glib-2.30.2" : {
				"EAPI": "5",
				"SLOT": "2/2.30"
			},
			"dev-libs/dbus-glib-0.98" : {
				"EAPI": "5",
				"DEPEND":  "dev-libs/glib:2/2.30=",
				"RDEPEND": "dev-libs/glib:2/2.30="
			},
		}

		world = ["dev-libs/glib:1", "dev-libs/dbus-glib"]

		test_cases = (

			ResolverPlaygroundTestCase(
				["dev-libs/glib"],
				options = {"--oneshot": True},
				success = True,
				mergelist = ["dev-libs/glib-2.32.3", "dev-libs/dbus-glib-0.98" ]),

			ResolverPlaygroundTestCase(
				["dev-libs/glib"],
				options = {"--oneshot": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["dev-libs/glib-2.32.3"]),

			ResolverPlaygroundTestCase(
				["dev-libs/glib"],
				options = {"--oneshot": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/glib-2.32.3", "dev-libs/dbus-glib-0.98" ]),

			ResolverPlaygroundTestCase(
				["dev-libs/glib"],
				options = {"--oneshot": True, "--usepkgonly": True},
				success = True,
				mergelist = ["[binary]dev-libs/glib-2.30.2"]),

			ResolverPlaygroundTestCase(
				["dev-libs/glib"],
				options = {"--oneshot": True, "--usepkgonly": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["[binary]dev-libs/glib-2.32.3"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = ["dev-libs/glib-2.32.3", "dev-libs/dbus-glib-0.98" ]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["dev-libs/glib-2.32.3"]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkg": True},
				success = True,
				mergelist = ["[binary]dev-libs/glib-2.32.3", "dev-libs/dbus-glib-0.98" ]),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkgonly": True},
				success = True,
				mergelist = []),

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True, "--usepkgonly": True, "--ignore-built-slot-operator-deps": "y"},
				success = True,
				mergelist = ["[binary]dev-libs/glib-2.32.3"]),

		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
