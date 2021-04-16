# Copyright 2014-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.repository.config import allow_profile_repo_deps
from portage.util import grabfile_package, stack_lists
from portage._sets.base import PackageSet

class ProfilePackageSet(PackageSet):
	_operations = ["merge"]

	def __init__(self, profiles, debug=False):
		super(ProfilePackageSet, self).__init__(
			allow_repo=any(allow_profile_repo_deps(y) for y in profiles)
		)
		self._profiles = profiles
		if profiles:
			desc_profile = profiles[-1]
			if desc_profile.user_config and len(profiles) > 1:
				desc_profile = profiles[-2]
			description = desc_profile.location
		else:
			description = None
		self.description = "Profile packages for profile %s" % description

	def load(self):
		self._setAtoms(x for x in stack_lists(
			[grabfile_package(os.path.join(y.location, "packages"),
			verify_eapi=True, eapi=y.eapi, eapi_default=None,
			allow_build_id=y.allow_build_id, allow_repo=allow_profile_repo_deps(y))
			for y in self._profiles
			if "profile-set" in y.profile_formats],
			incremental=1) if x[:1] != "*")

	def singleBuilder(self, options, settings, trees):
		return ProfilePackageSet(
			settings._locations_manager.profiles_complex)
	singleBuilder = classmethod(singleBuilder)
