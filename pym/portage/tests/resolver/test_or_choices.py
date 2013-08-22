# Copyright 2013 Gentoo Foundation
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
