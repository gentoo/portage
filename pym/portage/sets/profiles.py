# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
from portage.util import grabfile_package, stack_lists
from portage.sets import PackageSet

__all__ = ["PackagesSystemSet"]

class PackagesSystemSet(PackageSet):
	_operations = ["merge"]

	def __init__(self, profile_paths):
		super(PackagesSystemSet, self).__init__()
		self._profile_paths = profile_paths
		self.description = "System packages for profile %s" % self._profile_paths[-1]
	
	def load(self):
		mylist = [grabfile_package(os.path.join(x, "packages")) for x in self._profile_paths]
		mylist = stack_lists(mylist, incremental=1)
		self._setAtoms([x[1:] for x in mylist if x[0] == "*"])

	def singleBuilder(self, options, settings, trees):
		return PackagesSystemSet(settings.profiles)
	singleBuilder = classmethod(singleBuilder)
