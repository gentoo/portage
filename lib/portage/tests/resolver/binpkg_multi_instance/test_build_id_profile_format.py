# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (ResolverPlayground,
	ResolverPlaygroundTestCase)

class BuildIdProfileFormatTestCase(TestCase):

	def testBuildIdProfileFormat(self):

		profile = {
			"packages": ("=app-misc/A-1-2::test_repo",),
			"package.mask": ("<app-misc/A-1::test_repo",),
			"package.keywords": ("app-misc/A-1::test_repo x86",),
			"package.unmask": (">=app-misc/A-1::test_repo",),
			"package.use": ("app-misc/A-1::test_repo foo",),
			"package.use.mask": ("app-misc/A-1::test_repo -foo",),
			"package.use.stable.mask": ("app-misc/A-1::test_repo -foo",),
			"package.use.force": ("app-misc/A-1::test_repo foo",),
			"package.use.stable.force": ("app-misc/A-1::test_repo foo",),
			"package.provided": ("sys-libs/zlib-1.2.8-r1",),
		}

		repo_configs = {
			"test_repo": {
				"layout.conf": (
					"profile-formats = build-id profile-repo-deps profile-set",
				),
			}
		}

		user_config = {
			"make.conf":
				(
					"FEATURES=\"binpkg-multi-instance\"",
				),
		}

		ebuilds = {
			"app-misc/A-1" : {
				"EAPI": "5",
				"RDEPEND": "sys-libs/zlib dev-libs/B[foo]",
				"DEPEND": "sys-libs/zlib dev-libs/B[foo]",
			},
			"dev-libs/B-1" : {
				"EAPI": "5",
				"IUSE": "foo",
			},
		}

		binpkgs = (
			("app-misc/A-1", {
				"EAPI": "5",
				"BUILD_ID": "1",
				"BUILD_TIME": "1",
				"RDEPEND": "sys-libs/zlib dev-libs/B[foo]",
				"DEPEND": "sys-libs/zlib dev-libs/B[foo]",
			}),
			("app-misc/A-1", {
				"EAPI": "5",
				"BUILD_ID": "2",
				"BUILD_TIME": "2",
				"RDEPEND": "sys-libs/zlib dev-libs/B[foo]",
				"DEPEND": "sys-libs/zlib dev-libs/B[foo]",
			}),
			("app-misc/A-1", {
				"EAPI": "5",
				"BUILD_ID": "3",
				"BUILD_TIME": "3",
				"RDEPEND": "sys-libs/zlib dev-libs/B[foo]",
				"DEPEND": "sys-libs/zlib dev-libs/B[foo]",
			}),
			("dev-libs/B-1", {
				"EAPI": "5",
				"IUSE": "foo",
				"USE": "",
				"BUILD_ID": "1",
				"BUILD_TIME": "1",
			}),
			("dev-libs/B-1", {
				"EAPI": "5",
				"IUSE": "foo",
				"USE": "foo",
				"BUILD_ID": "2",
				"BUILD_TIME": "2",
			}),
			("dev-libs/B-1", {
				"EAPI": "5",
				"IUSE": "foo",
				"USE": "",
				"BUILD_ID": "3",
				"BUILD_TIME": "3",
			}),
		)

		installed = {
			"app-misc/A-1" : {
				"EAPI": "5",
				"BUILD_ID": "1",
				"BUILD_TIME": "1",
				"RDEPEND": "sys-libs/zlib",
				"DEPEND": "sys-libs/zlib",
			},
			"dev-libs/B-1" : {
				"EAPI": "5",
				"IUSE": "foo",
				"USE": "foo",
				"BUILD_ID": "2",
				"BUILD_TIME": "2",
			},
		}

		world = ()

		test_cases = (

			ResolverPlaygroundTestCase(
				["@world"],
				options = {"--emptytree": True, "--usepkgonly": True},
				success = True,
				mergelist = [
					"[binary]dev-libs/B-1-2",
					"[binary]app-misc/A-1-2"
				]
			),

		)

		playground = ResolverPlayground(debug=False,
			binpkgs=binpkgs, ebuilds=ebuilds, installed=installed,
			repo_configs=repo_configs, profile=profile,
			user_config=user_config, world=world)
		try:
			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)
		finally:
			# Disable debug so that cleanup works.
			#playground.debug = False
			playground.cleanup()
