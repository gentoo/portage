# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class SonameDepcleanTestCase(TestCase):

	def testSonameDepclean(self):

		installed = {
			"app-misc/A-1" : {
				"RDEPEND": "dev-libs/B",
				"DEPEND": "dev-libs/B",
				"REQUIRES": "x86_32: libB.so.1 libc.so.6",
			},
			"dev-libs/B-1" : {
				"PROVIDES": "x86_32: libB.so.1",
			},
			"sys-libs/glibc-2.19-r1" : {
				"PROVIDES": "x86_32: libc.so.6"
			},
		}

		world = ("app-misc/A",)

		test_cases = (

			ResolverPlaygroundTestCase(
				[],
				options={
					"--depclean": True,
					"--ignore-soname-deps": "n",
				},
				success=True,
				cleanlist=[]
			),

			ResolverPlaygroundTestCase(
				[],
				options={
					"--depclean": True,
					"--ignore-soname-deps": "y",
				},
				success=True,
				cleanlist=["sys-libs/glibc-2.19-r1"]
			),
		)

		playground = ResolverPlayground(debug=False,
			installed=installed, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			playground.debug = False
			playground.cleanup()
