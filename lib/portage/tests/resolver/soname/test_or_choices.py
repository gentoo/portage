# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SonameOrChoicesTestCase(TestCase):

	def testSonameConflictMissedUpdate(self):

		binpkgs = {
			"dev-lang/ocaml-4.02.1" : {
				"EAPI": "5",
				"PROVIDES": "x86_32: libocaml-4.02.1.so",
			},

			"dev-lang/ocaml-4.01.0" : {
				"EAPI": "5",
				"PROVIDES": "x86_32: libocaml-4.01.0.so",
			},

			"dev-ml/lablgl-1.05" : {
				"DEPEND": (">=dev-lang/ocaml-3.10.2 "
					"|| ( dev-ml/labltk <dev-lang/ocaml-4.02 )"),
				"RDEPEND": (">=dev-lang/ocaml-3.10.2 "
					"|| ( dev-ml/labltk <dev-lang/ocaml-4.02 )"),
				"REQUIRES": "x86_32: libocaml-4.02.1.so",
			},

			"dev-ml/labltk-8.06.0" : {
				"EAPI": "5",
				"SLOT": "0/8.06.0",
				"DEPEND": ">=dev-lang/ocaml-4.02",
				"RDEPEND": ">=dev-lang/ocaml-4.02",
				"REQUIRES": "x86_32: libocaml-4.02.1.so",
			},
		}

		installed = {
			"dev-lang/ocaml-4.01.0" : {
				"EAPI": "5",
				"PROVIDES": "x86_32: libocaml-4.01.0.so",
			},

			"dev-ml/lablgl-1.05" : {
				"DEPEND": (">=dev-lang/ocaml-3.10.2 "
					"|| ( dev-ml/labltk <dev-lang/ocaml-4.02 )"),
				"RDEPEND": (">=dev-lang/ocaml-3.10.2 "
					"|| ( dev-ml/labltk <dev-lang/ocaml-4.02 )"),
				"REQUIRES": "x86_32: libocaml-4.01.0.so",
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
				options = {
					"--deep": True,
					"--ignore-soname-deps": "n",
					"--update": True,
					"--usepkgonly": True
				},
				success = True,
				mergelist = [
					"[binary]dev-lang/ocaml-4.02.1",
					"[binary]dev-ml/labltk-8.06.0",
					"[binary]dev-ml/lablgl-1.05",
				]
			),

		)

		playground = ResolverPlayground(debug=False,
			binpkgs=binpkgs, installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			playground.debug = False
			playground.cleanup()
