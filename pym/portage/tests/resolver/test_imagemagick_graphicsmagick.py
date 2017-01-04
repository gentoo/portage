# Copyright 2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground,
	ResolverPlaygroundTestCase,
)

class ImageMagickGraphicsMagickTestCase(TestCase):

	def testImageMagickUpdate(self):

		ebuilds = {
			"media-gfx/imagemagick-6.9.7.0" : {
				"EAPI": "6",
				"SLOT": "0/6.9.7.0",
			},

			"media-gfx/imagemagick-6.9.6.6" : {
				"EAPI": "6",
				"SLOT": "0/6.9.6.6",
			},

			"media-gfx/inkscape-0.91-r3" : {
				"EAPI": "6",
				"DEPEND": "media-gfx/imagemagick:=",
				"RDEPEND": "media-gfx/imagemagick:=",
			},

			"media-video/dvdrip-0.98.11-r3" : {
				"EAPI": "6",
				"DEPEND": "|| ( media-gfx/graphicsmagick[imagemagick] media-gfx/imagemagick )",
				"RDEPEND": "|| ( media-gfx/graphicsmagick[imagemagick] media-gfx/imagemagick )",
			},

			"media-gfx/graphicsmagick-1.3.25" : {
				"EAPI": "6",
				"SLOT": "0/1.3",
				"IUSE": "imagemagick",
				"RDEPEND": "imagemagick? ( !media-gfx/imagemagick )",
			},
		}

		installed = {
			"media-gfx/imagemagick-6.9.6.6" : {
				"EAPI": "6",
				"SLOT": "0/6.9.6.6",
			},

			"media-gfx/inkscape-0.91-r3" : {
				"EAPI": "6",
				"DEPEND": "media-gfx/imagemagick:0/6.9.6.6=",
				"RDEPEND": "media-gfx/imagemagick:0/6.9.6.6=",
			},

			"media-video/dvdrip-0.98.11-r3" : {
				"EAPI": "6",
				"DEPEND": "|| ( media-gfx/graphicsmagick[imagemagick] media-gfx/imagemagick )",
				"RDEPEND": "|| ( media-gfx/graphicsmagick[imagemagick] media-gfx/imagemagick )",
			},

			"media-gfx/graphicsmagick-1.3.25" : {
				"EAPI": "6",
				"SLOT": "0/1.3",
				"IUSE": "imagemagick",
				"USE": "",
				"RDEPEND": "imagemagick? ( !media-gfx/imagemagick )",
			},
		}

		world = (
			"media-gfx/inkscape",
			"media-video/dvdrip",
			"media-gfx/graphicsmagick",
		)

		test_cases = (

			# bug #554070: imagemagick upgrade triggered erroneous
			# autounmask USE change for media-gfx/graphicsmagick[imagemagick]
			ResolverPlaygroundTestCase(
				["media-gfx/imagemagick", "@world"],
				options = {"--update": True, "--deep": True},
				success = True,
				mergelist = [
					"media-gfx/imagemagick-6.9.7.0",
					"media-gfx/inkscape-0.91-r3"
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
