#-*- coding:utf-8 -*-
# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
"""
Methods to check whether Portage is going to write to read-only filesystems.
Since the methods are not portable across different OSes, each OS needs its
own method. To expand RO checking for different OSes, add a method which
accepts a list of directories and returns a list of mounts which need to be
remounted RW, then add "elif ostype == (the ostype value for your OS)" to
get_ro_checker().
"""
import io
import logging
import os

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
	invalids = []

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
				mount = line.split(' - ', 1)
				try:
					_dir, attr1 = mount[0].split()[4:6]
				except ValueError:
					# If it raises ValueError we can simply ignore the line.
					invalids.append(line)
					continue
				# check for situation with invalid entries for /home and /root in /proc/self/mountinfo
				# root path is missing sometimes on WSL
				# for example: 16 1 0:16 / /root rw,noatime - lxfs  rw
				if len(mount) > 1:
					try:
						attr2 = mount[1].split()[2]
					except IndexError:
						try:
							attr2 = mount[1].split()[1]
						except IndexError:
							invalids.append(line)
							continue
				else:
					invalids.append(line)
					continue
				if attr1.startswith('ro') or attr2.startswith('ro'):
					ro_filesystems.add(_dir)

	# If /proc/self/mountinfo can't be read, assume that there are no RO
	# filesystems and return.
	except EnvironmentError:
		writemsg_level(_("!!! /proc/self/mountinfo cannot be read"),
			level=logging.WARNING, noiselevel=-1)
		return []

	for line in invalids:
		writemsg_level(_("!!! /proc/self/mountinfo contains unrecognized line: %s\n")
			% line.rstrip(), level=logging.WARNING, noiselevel=-1)

	ro_devs = {}
	for x in ro_filesystems:
		try:
			ro_devs[os.stat(x).st_dev] = x
		except OSError:
			pass

	ro_filesystems.clear()
	for x in set(dir_list):
		try:
			dev = os.stat(x).st_dev
		except OSError:
			pass
		else:
			try:
				ro_filesystems.add(ro_devs[dev])
			except KeyError:
				pass

	return ro_filesystems


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
