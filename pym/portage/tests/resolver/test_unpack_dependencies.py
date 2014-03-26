# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground, ResolverPlaygroundTestCase

class UnpackDependenciesTestCase(TestCase):
	def testUnpackDependencies(self):
		distfiles = {
			"A-1.tar.gz": b"binary\0content",
			"B-1.TAR.XZ": b"binary\0content",
			"B-docs-1.tar.bz2": b"binary\0content",
			"C-1.TAR.XZ": b"binary\0content",
			"C-docs-1.tar.bz2": b"binary\0content",
		}

		ebuilds = {
			"dev-libs/A-1": {"SRC_URI": "A-1.tar.gz", "EAPI": "5-progress"},
			"dev-libs/B-1": {"IUSE": "doc", "SRC_URI": "B-1.TAR.XZ doc? ( B-docs-1.tar.bz2 )", "EAPI": "5-progress"},
			"dev-libs/C-1": {"IUSE": "doc", "SRC_URI": "C-1.TAR.XZ doc? ( C-docs-1.tar.bz2 )", "EAPI": "5-progress"},
			"app-arch/bzip2-1": {},
			"app-arch/gzip-1": {},
			"app-arch/tar-1": {},
			"app-arch/xz-utils-1": {},
		}

		repo_configs = {
			"test_repo": {
				"unpack_dependencies/5-progress": (
					"tar.bz2 app-arch/tar app-arch/bzip2",
					"tar.gz app-arch/tar app-arch/gzip",
					"tar.xz app-arch/tar app-arch/xz-utils",
				),
			},
		}

		test_cases = (
			ResolverPlaygroundTestCase(
				["dev-libs/A"],
				success = True,
				ignore_mergelist_order = True,
				mergelist = ["app-arch/tar-1", "app-arch/gzip-1", "dev-libs/A-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/B"],
				success = True,
				ignore_mergelist_order = True,
				mergelist = ["app-arch/tar-1", "app-arch/xz-utils-1", "dev-libs/B-1"]),
			ResolverPlaygroundTestCase(
				["dev-libs/C"],
				success = True,
				ignore_mergelist_order = True,
				mergelist = ["app-arch/tar-1", "app-arch/xz-utils-1", "app-arch/bzip2-1", "dev-libs/C-1"]),
		)

		user_config = {
			"package.use": ("dev-libs/C doc",)
		}

		playground = ResolverPlayground(distfiles=distfiles, ebuilds=ebuilds, repo_configs=repo_configs, user_config=user_config)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True, test_case.fail_msg)
		finally:
			playground.cleanup()
