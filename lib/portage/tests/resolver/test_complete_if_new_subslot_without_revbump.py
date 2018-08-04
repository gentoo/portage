# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class CompeteIfNewSubSlotWithoutRevBumpTestCase(TestCase):

	def testCompeteIfNewSubSlotWithoutRevBump(self):

		ebuilds = {
			"media-libs/libpng-1.5.14" : {
				"EAPI": "5",
				"SLOT": "0"
			},

			"x11-libs/gdk-pixbuf-2.26.5" : {
				"EAPI": "5",
				"DEPEND": ">=media-libs/libpng-1.4:=",
				"RDEPEND": ">=media-libs/libpng-1.4:="
			},
		}

		binpkgs = {
			"x11-libs/gdk-pixbuf-2.26.5" : {
				"EAPI": "5",
				"DEPEND": ">=media-libs/libpng-1.4:0/15=",
				"RDEPEND": ">=media-libs/libpng-1.4:0/15="
			},
		}

		installed = {
			"media-libs/libpng-1.5.14" : {
				"EAPI": "5",
				"SLOT": "0/15"
			},

			"x11-libs/gdk-pixbuf-2.26.5" : {
				"EAPI": "5",
				"DEPEND": ">=media-libs/libpng-1.4:0/15=",
				"RDEPEND": ">=media-libs/libpng-1.4:0/15="
			},
		}

		world = ["x11-libs/gdk-pixbuf"]

		test_cases = (
			# Test that --complete-graph-if-new-ver=y triggers rebuild
			# when the sub-slot changes without a revbump.
			ResolverPlaygroundTestCase(
				["media-libs/libpng"],
				options = {
					"--oneshot": True,
					"--complete-graph-if-new-ver": "y",
					"--rebuild-if-new-slot": "n",
					"--usepkg": True
				},
				success = True,
				mergelist = [
					"media-libs/libpng-1.5.14",
					"x11-libs/gdk-pixbuf-2.26.5"
				]
			),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, binpkgs=binpkgs,
			installed=installed, world=world, debug=False)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
