# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging

from portage import os
from portage.util import grabfile_package, stack_lists
from portage._sets.base import PackageSet
from portage._sets import get_boolean
from portage.util import writemsg_level

__all__ = ["PackagesSystemSet"]

class PackagesSystemSet(PackageSet):
	_operations = ["merge"]

	def __init__(self, profile_paths, debug=False):
		super(PackagesSystemSet, self).__init__()
		self._profile_paths = profile_paths
		self._debug = debug
		if profile_paths:
			description = self._profile_paths[-1]
			if description == "/etc/portage/profile" and \
				len(self._profile_paths) > 1:
				description = self._profile_paths[-2]
		else:
			description = None
		self.description = "System packages for profile %s" % description

	def load(self):
		debug = self._debug
		if debug:
			writemsg_level("\nPackagesSystemSet: profile paths: %s\n" % \
				(self._profile_paths,), level=logging.DEBUG, noiselevel=-1)

		mylist = [grabfile_package(os.path.join(x, "packages"), verify_eapi=True) for x in self._profile_paths]

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
		return PackagesSystemSet(settings.profiles, debug=debug)
	singleBuilder = classmethod(singleBuilder)
