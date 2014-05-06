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
	Use /proc/self/mountinfo to check that no directories installed by the
	ebuild are set to be installed to a read-only filesystem.

	@param dir_list: A list of directories installed by the ebuild.
	@type dir_list: List
	@return:
	1. A list of filesystems which are both set to be written to and are mounted
	read-only, may be empty.
	"""
	ro_filesystems = set()

	try:
		with io.open("/proc/self/mountinfo", mode='r',
			encoding=_encodings['content'], errors='replace') as f:
			for line in f:
				# we're interested in dir and both attr fileds which always
				# start with either 'ro' or 'rw'
				# example line:
				# 14 1 8:3 / / rw,noatime - ext3 /dev/root rw,errors=continue,commit=5,barrier=1,data=writeback
				#       _dir ^ ^ attr1                     ^ attr2
				# there can be a variable number of fields
				# to the left of the ' - ', after the attr's, so split it there
				mount = line.split(' - ')
				_dir, attr1 = mount[0].split()[4:6]
				attr2 = mount[1].split()[2]
				if attr1.startswith('ro') or attr2.startswith('ro'):
					ro_filesystems.add(_dir)

	# If /proc/self/mountinfo can't be read, assume that there are no RO
	# filesystems and return.
	except EnvironmentError:
		writemsg_level(_("!!! /proc/self/mountinfo cannot be read"),
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
