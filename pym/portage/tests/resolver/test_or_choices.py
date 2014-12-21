# Copyright 2013-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class OrChoicesTestCase(TestCase):

	def testOrChoices(self):
		ebuilds = {
			"dev-lang/vala-0.20.0" : {
				"EAPI": "5",
				"SLOT": "0.20"
			},
			"dev-lang/vala-0.18.0" : {
				"EAPI": "5",
				"SLOT": "0.18"
			},
			#"dev-libs/gobject-introspection-1.36.0" : {
			#	"EAPI": "5",
			#	"RDEPEND" : "!<dev-lang/vala-0.20.0",
			#},
			"dev-libs/gobject-introspection-1.34.0" : {
				"EAPI": "5"
			},
			"sys-apps/systemd-ui-2" : {
				"EAPI": "5",
				"RDEPEND" : "|| ( dev-lang/vala:0.20 dev-lang/vala:0.18 )"
			},
		}

		installed = {
			"dev-lang/vala-0.18.0" : {
				"EAPI": "5",
				"SLOT": "0.18"
			},
			"dev-libs/gobject-introspection-1.34.0" : {
				"EAPI": "5"
			},
			"sys-apps/systemd-ui-2" : {
				"EAPI": "5",
				"RDEPEND" : "|| ( dev-lang/vala:0.20 dev-lang/vala:0.18 )"
			},
		}

		world = ["dev-libs/gobject-introspection", "sys-apps/systemd-ui"]

		test_cases = (
			# Demonstrate that vala:0.20 update is pulled in, for bug #478188
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success=True,
				all_permutations = True,
				mergelist = ['dev-lang/vala-0.20.0']),
			# Verify that vala:0.20 is not pulled in without --deep
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True},
				success=True,
				all_permutations = True,
				mergelist = []),
			# Verify that vala:0.20 is not pulled in without --update
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--selective": True, "--deep": True},
				success=True,
				all_permutations = True,
				mergelist = []),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()

	def testOrChoicesLibpostproc(self):
		ebuilds = {
			"media-video/ffmpeg-0.10" : {
				"EAPI": "5",
				"SLOT": "0.10"
			},
			"media-video/ffmpeg-1.2.2" : {
				"EAPI": "5",
				"SLOT": "0"
			},
			"media-libs/libpostproc-0.8.0.20121125" : {
				"EAPI": "5"
			},
			"media-plugins/gst-plugins-ffmpeg-0.10.13_p201211-r1" : {
				"EAPI": "5",
				"RDEPEND" : "|| ( media-video/ffmpeg:0 media-libs/libpostproc )"
			},
		}

		installed = {
			"media-video/ffmpeg-0.10" : {
				"EAPI": "5",
				"SLOT": "0.10"
			},
			"media-libs/libpostproc-0.8.0.20121125" : {
				"EAPI": "5"
			},
			"media-plugins/gst-plugins-ffmpeg-0.10.13_p201211-r1" : {
				"EAPI": "5",
				"RDEPEND" : "|| ( media-video/ffmpeg:0 media-libs/libpostproc )"
			},
		}

		world = ["media-plugins/gst-plugins-ffmpeg"]

		test_cases = (
			# Demonstrate that libpostproc is preferred
			# over ffmpeg:0 for bug #480736.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success=True,
				all_permutations = True,
				mergelist = []),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed,
			world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testInitiallyUnsatisfied(self):

		ebuilds = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/A-2" : {
				"EAPI": "5",
				"SLOT": "0/2"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/A:="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"RDEPEND": "|| ( app-misc/X <app-misc/A-2 )"
			},

		}

		installed = {

			"app-misc/A-1" : {
				"EAPI": "5",
				"SLOT": "0/1"
			},

			"app-misc/B-0" : {
				"EAPI": "5",
				"RDEPEND": "app-misc/A:0/1="
			},

			"app-misc/C-0" : {
				"EAPI": "5",
				"RDEPEND": "|| ( app-misc/X <app-misc/A-2 )"
			},

		}

		world = ["app-misc/B", "app-misc/C"]

		test_cases = (

			# Test bug #522652, where the unsatisfiable app-misc/X
			# atom is selected, and the dependency is placed into
			# _initially_unsatisfied_deps where it is ignored, causing
			# upgrade to app-misc/A-2 (breaking a dependency of
			# app-misc/C-0).
			ResolverPlaygroundTestCase(
				["app-misc/A"],
				options = {},
				success = True,
				mergelist = ['app-misc/A-1']
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()


	def testUseMask(self):

		profile = {
			"use.mask":
			(
				"abi_ppc_32",
			),
		}

		ebuilds = {

			"sys-libs/A-1" : {
				"EAPI": "5",
				"RDEPEND": "|| ( sys-libs/zlib[abi_ppc_32(-)] " + \
					"sys-libs/zlib[abi_x86_32(-)] )"
			},

			"sys-libs/zlib-1.2.8-r1" : {
				"EAPI": "5",
				"IUSE": "abi_ppc_32 abi_x86_32"
			},

			"sys-libs/zlib-1.2.8" : {
				"EAPI": "5",
				"IUSE": ""
			},
		}

		test_cases = (

			# bug #515584: We want to prefer choices that do
			# not require changes to use.mask or use.force.
			# In this case, abi_ppc_32 is use.masked in the
			# profile, so we want to avoid that choice.
			ResolverPlaygroundTestCase(
				["sys-libs/A"],
				options = {},
				success = False,
				use_changes = {
					'sys-libs/zlib-1.2.8-r1': {'abi_x86_32': True}
				},
				mergelist = ["sys-libs/zlib-1.2.8-r1", "sys-libs/A-1"]
			),

		)

		playground = ResolverPlayground(ebuilds=ebuilds,
			profile=profile, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			playground.cleanup()

	def testConflictMissedUpdate(self):

		ebuilds = {
			"dev-lang/ocaml-4.02.1" : {
				"EAPI": "5",
				"SLOT": "0/4.02.1",
			},

			"dev-lang/ocaml-4.01.0" : {
				"EAPI": "5",
				"SLOT": "0/4.01.0",
			},

			"dev-ml/lablgl-1.05" : {
				"EAPI": "5",
				"DEPEND": (">=dev-lang/ocaml-3.10.2:= "
					"|| ( dev-ml/labltk:= <dev-lang/ocaml-4.02 )"),
				"RDEPEND": (">=dev-lang/ocaml-3.10.2:= "
					"|| ( dev-ml/labltk:= <dev-lang/ocaml-4.02 )"),
			},

			"dev-ml/labltk-8.06.0" : {
				"EAPI": "5",
				"SLOT": "0/8.06.0",
				"DEPEND": ">=dev-lang/ocaml-4.02:=",
				"RDEPEND": ">=dev-lang/ocaml-4.02:=",
			},
		}

		installed = {
			"dev-lang/ocaml-4.01.0" : {
				"EAPI": "5",
				"SLOT": "0/4.01.0",
			},

			"dev-ml/lablgl-1.05" : {
				"EAPI": "5",
				"DEPEND": (">=dev-lang/ocaml-3.10.2:0/4.01.0= "
					"|| ( dev-ml/labltk:= <dev-lang/ocaml-4.02 )"),
				"RDEPEND": (">=dev-lang/ocaml-3.10.2:0/4.01.0= "
					"|| ( dev-ml/labltk:= <dev-lang/ocaml-4.02 )"),
			},
		}

		world = (
			"dev-lang/ocaml",
			"dev-ml/lablgl",
		)

		test_cases = (

			# bug #531656: If an ocaml update is desirable,
			# then we need to pull in dev-ml/labltk.
			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = [
					"dev-lang/ocaml-4.02.1",
					"dev-ml/labltk-8.06.0",
					"dev-ml/lablgl-1.05",
				]
			),

		)

		playground = ResolverPlayground(debug=False,
			ebuilds=ebuilds, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			playground.debug = False
			playground.cleanup()
