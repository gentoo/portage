# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io

from portage import os, _encodings
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import (
	ResolverPlayground, ResolverPlaygroundTestCase)
from portage.util import ensure_dirs

class ProfilePackageSetTestCase(TestCase):

	def testProfilePackageSet(self):

		repo_configs = {
			"test_repo": {
				"layout.conf": ("profile-formats = profile-set",),
			}
		}

		profiles = (
			(
				'default/linux',
				{
					"eapi": ("5",),
					"packages": (
						"*sys-libs/A",
						"app-misc/A",
						"app-misc/B",
						"app-misc/C",
					),
				}
			),
			(
				'default/linux/x86',
				{
					"eapi": ("5",),
					"packages": (
						"-app-misc/B",
					),
					"parent": ("..",)
				}
			),
		)

		ebuilds = {
			"sys-libs/A-1": {
				"EAPI": "5",
			},
			"app-misc/A-1": {
				"EAPI": "5",
			},
			"app-misc/B-1": {
				"EAPI": "5",
			},
			"app-misc/C-1": {
				"EAPI": "5",
			},
		}

		installed = {
			"sys-libs/A-1": {
				"EAPI": "5",
			},
			"app-misc/A-1": {
				"EAPI": "5",
			},
			"app-misc/B-1": {
				"EAPI": "5",
			},
			"app-misc/C-1": {
				"EAPI": "5",
			},
		}

		test_cases = (

			ResolverPlaygroundTestCase(
				["@world"],
				options={"--update": True, "--deep": True},
				mergelist = [],
				success = True,
			),

			ResolverPlaygroundTestCase(
				[],
				options={"--depclean": True},
				success=True,
				cleanlist=["app-misc/B-1"]
			),

		)

		playground = ResolverPlayground(debug=False, ebuilds=ebuilds,
			installed=installed, repo_configs=repo_configs)
		try:
			repo_dir = (playground.settings.repositories.
				get_location_for_name("test_repo"))
			profile_root = os.path.join(repo_dir, "profiles")

			for p, data in profiles:
				prof_path = os.path.join(profile_root, p)
				ensure_dirs(prof_path)
				for k, v in data.items():
					with io.open(os.path.join(prof_path, k), mode="w",
						encoding=_encodings["repo.content"]) as f:
						for line in v:
							f.write("%s\n" % line)

			# The config must be reloaded in order to account
			# for the above profile customizations.
			playground.reload_config()

			for test_case in test_cases:
				playground.run_TestCase(test_case)
				self.assertEqual(test_case.test_success, True,
					test_case.fail_msg)

		finally:
			playground.cleanup()
