# Copyright 2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class RegularSlotChangeWithoutRevBumpTestCase(TestCase):

	def testRegularSlotChangeWithoutRevBumpTestCase(self):

		ebuilds = {
			"dev-libs/boost-1.52.0" : {
				"SLOT": "0"
			},
			"app-office/libreoffice-4.0.0.2" : {
				"EAPI": "5",
				"DEPEND": ">=dev-libs/boost-1.46:=",
				"RDEPEND": ">=dev-libs/boost-1.46:=",
			},
		}

		binpkgs = {
			"dev-libs/boost-1.52.0" : {
				"SLOT": "1.52"
			},
		}

		installed = {
			"dev-libs/boost-1.52.0" : {
				"SLOT": "1.52"
			},
		}

		world = []

		test_cases = (
			# Test that @__auto_slot_operator_replace_installed__
			# pulls in the available slot, even though it's
			# different from the installed slot (0 instead of 1.52).
			ResolverPlaygroundTestCase(
				["app-office/libreoffice"],
				options = {"--oneshot": True, "--usepkg": True},
				success = True,
				mergelist = [
					'dev-libs/boost-1.52.0',
					'app-office/libreoffice-4.0.0.2'
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
