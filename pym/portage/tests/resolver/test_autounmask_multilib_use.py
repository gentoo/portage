# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class AutounmaskMultilibUseTestCase(TestCase):

	def testAutounmaskMultilibUse(self):

		self.todo = True

		ebuilds = {
			"x11-proto/xextproto-7.2.1-r1": {
				"EAPI": "5",
				"IUSE": "abi_x86_32 abi_x86_64",
			},
			"x11-libs/libXaw-1.0.11-r2": {
				"EAPI": "5",
				"IUSE": "abi_x86_32 abi_x86_64",
				"RDEPEND": "x11-proto/xextproto[abi_x86_32(-)?,abi_x86_64(-)?]"
			},
			"app-emulation/emul-linux-x86-xlibs-20130224-r2": {
				"EAPI": "5",
				"RDEPEND": "x11-libs/libXaw[abi_x86_32]"
			},
			"games-util/steam-client-meta-0-r20130514": {
				"EAPI": "5",
				"RDEPEND": "app-emulation/emul-linux-x86-xlibs"
			}
		}

		installed = {
			"x11-proto/xextproto-7.2.1-r1": {
				"EAPI": "5",
				"IUSE": "abi_x86_32 abi_x86_64",
				"USE": "abi_x86_32 abi_x86_64"
			},
			"x11-libs/libXaw-1.0.11-r2": {
				"EAPI": "5",
				"IUSE": "abi_x86_32 abi_x86_64",
				"RDEPEND": "x11-proto/xextproto[abi_x86_32(-)?,abi_x86_64(-)?]",
				"USE": "abi_x86_32 abi_x86_64"
			},
			"app-emulation/emul-linux-x86-xlibs-20130224-r2": {
				"EAPI": "5",
				"RDEPEND": "x11-libs/libXaw[abi_x86_32]"
			},
			"games-util/steam-client-meta-0-r20130514": {
				"EAPI": "5",
				"RDEPEND": "app-emulation/emul-linux-x86-xlibs"
			}
		}

		user_config = {
			#"make.conf" : ("USE=\"abi_x86_32 abi_x86_64\"",)
			"make.conf" : ("USE=\"abi_x86_64\"",)
		}

		world = ("games-util/steam-client-meta",)

		test_cases = (

				# Test autounmask solving of multilib use deps for bug #481628.
				# We would like it to suggest some USE changes, but instead it
				# currently fails with a SLOT conflict.

				ResolverPlaygroundTestCase(
					["x11-proto/xextproto", "x11-libs/libXaw"],
					options = {"--oneshot": True, "--autounmask": True,
						"--backtrack": 30},
					mergelist = ["x11-proto/xextproto-7.2.1-r1", "x11-libs/libXaw-1.0.11-r2"],
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed,
			user_config=user_config, world=world, debug=False)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
