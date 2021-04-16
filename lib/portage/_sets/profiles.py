# Copyright 2007-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging

from portage import os
from portage.repository.config import allow_profile_repo_deps
from portage.util import grabfile_package, stack_lists
from portage._sets.base import PackageSet
from portage._sets import get_boolean
from portage.util import writemsg_level

__all__ = ["PackagesSystemSet"]

class PackagesSystemSet(PackageSet):
	_operations = ["merge"]

	def __init__(self, profiles, debug=False):
		super(PackagesSystemSet, self).__init__(
			allow_repo=any(allow_profile_repo_deps(x) for x in profiles)
		)
		self._profiles = profiles
		self._debug = debug
		if profiles:
			desc_profile = profiles[-1]
			if desc_profile.user_config and len(profiles) > 1:
				desc_profile = profiles[-2]
			description = desc_profile.location
		else:
			description = None
		self.description = "System packages for profile %s" % description

	def load(self):
		debug = self._debug
		if debug:
			writemsg_level("\nPackagesSystemSet: profiles: %s\n" %
				(self._profiles,), level=logging.DEBUG, noiselevel=-1)

		mylist = [grabfile_package(os.path.join(x.location, "packages"),
			verify_eapi=True, eapi=x.eapi, eapi_default=None,
			allow_build_id=x.allow_build_id,
			allow_repo=allow_profile_repo_deps(x))
			for x in self._profiles]

		if debug:
			writemsg_level("\nPackagesSystemSet: raw packages: %s\n" % \
				(mylist,), level=logging.DEBUG, noiselevel=-1)

		mylist = stack_lists(mylist, incremental=1)

		if debug:
			writemsg_level("\nPackagesSystemSet: stacked packages: %s\n" % \
				(mylist,), level=logging.DEBUG, noiselevel=-1)

		self._setAtoms([x[1:] for x in mylist if x[0] == "*"])

	def singleBuilder(self, options, settings, trees):
		debug = get_boolean(options, "debug", False)
		return PackagesSystemSet(
			settings._locations_manager.profiles_complex, debug=debug)
	singleBuilder = classmethod(singleBuilder)
