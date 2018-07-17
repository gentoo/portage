# Copyright 2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class RebuildTestCase(TestCase):

	def testRebuild(self):
		"""
		Rebuild packages when build-time dependencies are upgraded.
		"""

		ebuilds = {
			"sys-libs/x-1": { },
			"sys-libs/x-1-r1": { },
			"sys-libs/x-2": { },
			"sys-apps/a-1": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/a-2": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/b-1": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/b-2": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/c-1": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/c-2": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/d-1": { "RDEPEND" : "sys-libs/x"},
			"sys-apps/d-2": { "RDEPEND" : "sys-libs/x"},
			"sys-apps/e-2": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/f-2": { "DEPEND"  : "sys-apps/a", "RDEPEND" : ""},
			"sys-apps/g-2": { "DEPEND"  : "sys-apps/b sys-libs/x",
				"RDEPEND" : ""},
			}

		installed = {
			"sys-libs/x-1": { },
			"sys-apps/a-1": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/b-1": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/c-1": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/d-1": { "RDEPEND" : "sys-libs/x"},
			"sys-apps/e-1": { "DEPEND"  : "sys-libs/x", "RDEPEND" : ""},
			"sys-apps/f-1": { "DEPEND"  : "sys-apps/a", "RDEPEND" : ""},
			"sys-apps/g-1": { "DEPEND"  : "sys-apps/b",
				"RDEPEND" : ""},
			}

		world = ["sys-apps/a", "sys-apps/b", "sys-apps/c", "sys-apps/d",
			"sys-apps/e", "sys-apps/f", "sys-apps/g"]


		test_cases = (
				ResolverPlaygroundTestCase(
					["sys-libs/x", "sys-apps/b"],
					options = {"--rebuild-if-unbuilt" : True,
						"--rebuild-exclude" : ["sys-apps/c"]},
					mergelist = ['sys-libs/x-2', 'sys-apps/a-2', 'sys-apps/b-2',
						'sys-apps/e-2', 'sys-apps/g-2'],
					ignore_mergelist_order = True,
					success = True),

				ResolverPlaygroundTestCase(
					["sys-libs/x", "sys-apps/b"],
					options = {"--rebuild-if-unbuilt" : True},
					mergelist = ['sys-libs/x-2', 'sys-apps/a-2', 'sys-apps/b-2',
						'sys-apps/c-2', 'sys-apps/e-2', 'sys-apps/g-2'],
					ignore_mergelist_order = True,
					success = True),

				ResolverPlaygroundTestCase(
					["sys-libs/x"],
					options = {"--rebuild-if-unbuilt" : True,
						"--rebuild-ignore" : ["sys-libs/x"]},
					mergelist = ['sys-libs/x-2'],
					ignore_mergelist_order = True,
					success = True),

				ResolverPlaygroundTestCase(
					["sys-libs/x", "sys-apps/b"],
					options = {"--rebuild-if-unbuilt" : True,
						"--rebuild-ignore" : ["sys-apps/b"]},
					mergelist = ['sys-libs/x-2', 'sys-apps/a-2', 'sys-apps/b-2',
						'sys-apps/c-2', 'sys-apps/e-2'],
					ignore_mergelist_order = True,
					success = True),

				ResolverPlaygroundTestCase(
					["=sys-libs/x-1-r1", "sys-apps/b"],
					options = {"--rebuild-if-unbuilt" : True},
					mergelist = ['sys-libs/x-1-r1', 'sys-apps/a-2',
						'sys-apps/b-2', 'sys-apps/c-2', 'sys-apps/e-2',
						'sys-apps/g-2'],
					ignore_mergelist_order = True,
					success = True),

				ResolverPlaygroundTestCase(
					["=sys-libs/x-1-r1", "sys-apps/b"],
					options = {"--rebuild-if-new-rev" : True},
					mergelist = ['sys-libs/x-1-r1', 'sys-apps/a-2',
						'sys-apps/b-2', 'sys-apps/c-2', 'sys-apps/e-2',
						'sys-apps/g-2'],
					ignore_mergelist_order = True,
					success = True),

				ResolverPlaygroundTestCase(
					["=sys-libs/x-1-r1"],
					options = {"--rebuild-if-new-ver" : True},
					mergelist = ['sys-libs/x-1-r1'],
					ignore_mergelist_order = True,
					success = True),

				ResolverPlaygroundTestCase(
					["sys-libs/x", "sys-apps/b"],
					options = {"--rebuild-if-new-ver" : True},
					mergelist = ['sys-libs/x-2', 'sys-apps/a-2',
						'sys-apps/b-2', 'sys-apps/c-2', 'sys-apps/e-2',
						'sys-apps/g-2'],
					ignore_mergelist_order = True,
					success = True),

				ResolverPlaygroundTestCase(
					["=sys-libs/x-1"],
					options = {"--rebuild-if-new-rev" : True},
					mergelist = ['sys-libs/x-1'],
					ignore_mergelist_order = True,
					success = True),

				ResolverPlaygroundTestCase(
					["=sys-libs/x-1", "=sys-apps/b-1"],
					options = {"--rebuild-if-unbuilt" : True},
					mergelist = ['sys-libs/x-1', 'sys-apps/a-2',
						'sys-apps/b-1', 'sys-apps/c-2', 'sys-apps/e-2',
						'sys-apps/g-2'],
					ignore_mergelist_order = True,
					success = True),
			)

		playground = ResolverPlayground(ebuilds=ebuilds,
			installed=installed, world=world)

		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
