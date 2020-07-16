# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io

from portage import os, _encodings
from portage.const import USER_CONFIG_PATH
from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground
from portage.dep import ExtendedAtomDict
from portage.util import ensure_dirs

class ProfileDefaultEAPITestCase(TestCase):

	def testProfileDefaultEAPI(self):

		repo_configs = {
			"test_repo": {
				"layout.conf": (
					"profile-formats = profile-default-eapi",
					"profile_eapi_when_unspecified = 5"
				),
			}
		}

		profiles = (
			(
				"",
				{
					"package.mask": ("sys-libs/A:1",),
					"package.use": ("sys-libs/A:1 flag",)
				}
			),
			(
				"default/linux",
				{
					"package.mask": ("sys-libs/B:1",),
					"package.use": ("sys-libs/B:1 flag",),
					"package.keywords": ("sys-libs/B:1 x86",)
				}
			),
			(
				"default/linux/x86",
				{
					"package.mask": ("sys-libs/C:1",),
					"package.use": ("sys-libs/C:1 flag",),
					"package.keywords": ("sys-libs/C:1 x86",),
					"parent": ("..",)
				}
			),
		)

		user_profile = {
			"package.mask": ("sys-libs/D:1",),
			"package.use": ("sys-libs/D:1 flag",),
			"package.keywords": ("sys-libs/D:1 x86",),
		}

		test_cases = (
			(lambda x: x._mask_manager._pmaskdict, {
				"sys-libs/A": ("sys-libs/A:1::test_repo",),
				"sys-libs/B": ("sys-libs/B:1",),
				"sys-libs/C": ("sys-libs/C:1",),
				"sys-libs/D": ("sys-libs/D:1",),
			}),
			(lambda x: x._use_manager._repo_puse_dict, {
				"test_repo": {
					"sys-libs/A": {
						"sys-libs/A:1": ("flag",)
					}
				}
			}),
			(lambda x: x._use_manager._pkgprofileuse, (
				{"sys-libs/B": {"sys-libs/B:1": "flag"}},
				{"sys-libs/C": {"sys-libs/C:1": "flag"}},
				{},
				{"sys-libs/D": {"sys-libs/D:1": "flag"}},
			)),
			(lambda x: x._keywords_manager._pkeywords_list, (
					{"sys-libs/B": {"sys-libs/B:1": ["x86"]}},
					{"sys-libs/C": {"sys-libs/C:1": ["x86"]}},
					{"sys-libs/D": {"sys-libs/D:1": ["x86"]}},
				)
			)
		)

		playground = ResolverPlayground(debug=False,
			repo_configs=repo_configs)
		try:
			repo_dir = (playground.settings.repositories.
				get_location_for_name("test_repo"))
			profile_root = os.path.join(repo_dir, "profiles")
			profile_info = [(os.path.join(profile_root, p), data)
				for p, data in profiles]
			profile_info.append((os.path.join(playground.eroot,
				USER_CONFIG_PATH, "profile"), user_profile))

			for prof_path, data in profile_info:
				ensure_dirs(prof_path)
				for k, v in data.items():
					with io.open(os.path.join(prof_path, k), mode="w",
						encoding=_encodings["repo.content"]) as f:
						for line in v:
							f.write("%s\n" % line)

			# The config must be reloaded in order to account
			# for the above profile customizations.
			playground.reload_config()

			for fn, expected in test_cases:
				result = self._translate_result(fn(playground.settings))
				self.assertEqual(result, expected)

		finally:
			playground.cleanup()


	@staticmethod
	def _translate_result(result):
		if isinstance(result, ExtendedAtomDict):
			result = dict(result.items())
		elif isinstance(result, tuple):
			result = tuple(dict(x.items()) for x in result)
		return result
