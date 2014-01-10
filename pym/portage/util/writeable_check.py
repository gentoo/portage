#-*- coding:utf-8 -*-
# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
"""
Methods to check whether Portage is going to write to read-only filesystems.
Since the methods are not portable across different OSes, each OS needs its
own method. To expand RO checking for different OSes, add a method which
accepts a list of directories and returns a list of mounts which need to be
remounted RW, then add "elif ostype == (the ostype value for your OS)" to
get_ro_checker().
"""
from __future__ import unicode_literals

import io
import logging
import re

from portage import _encodings
from portage.util import writemsg_level
from portage.localization import _
from portage.data import ostype


def get_ro_checker():
	"""
	Uses the system type to find an appropriate method for testing whether Portage
	is going to write to any read-only filesystems.

	@return:
	1. A method for testing for RO filesystems appropriate to the current system.
	"""
	return _CHECKERS.get(ostype, empty_ro_checker)


def linux_ro_checker(dir_list):
	"""
	Use /proc/mounts to check that no directories installed by the ebuild are set
	to be installed to a read-only filesystem.

	@param dir_list: A list of directories installed by the ebuild.
	@type dir_list: List
	@return:
	1. A list of filesystems which are both set to be written to and are mounted
	read-only, may be empty.
	"""
	ro_filesystems = set()

	try:
		with io.open("/proc/mounts", mode='r', encoding=_encodings['content'],
			errors='replace') as f:
			roregex = re.compile(r'(\A|,)ro(\Z|,)')
			for line in f:
				if roregex.search(line.split(" ")[3].strip()) is not None:
					romount = line.split(" ")[1].strip()
					ro_filesystems.add(romount)

	# If /proc/mounts can't be read, assume that there are no RO
	# filesystems and return.
	except EnvironmentError:
		writemsg_level(_("!!! /proc/mounts cannot be read"),
			level=logging.WARNING, noiselevel=-1)
		return []

	return set.intersection(ro_filesystems, set(dir_list))


def empty_ro_checker(dir_list):
	"""
	Always returns [], this is the fallback function if the system does not have
	an ro_checker method defined.
	"""
	return []


# _CHECKERS is a map from ostype output to the appropriate function to return
# in get_ro_checker.
_CHECKERS = {
	"Linux": linux_ro_checker,
}
