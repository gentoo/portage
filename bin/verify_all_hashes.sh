#!/bin/bash
#
# Copyright 2022 Daniel Dwek
#
# This file is part of Portage.
#
# Portage is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# version 2 as published by the Free Software Foundation.
#
# Portage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Portage; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.
#

#
# Let's browse recursively the installed packages on the system
# and check MD5 message digests for each object file listed on
# "CONTENTS" files, in order to verify right integrities.
# Please note that we use inverted back references with the "sed"
# command because we need to add an extra blank space between
# the hash sum and the filename processed.
#
# This script is intended to be used by Gentoo Authors or maintainers before
# either releasing new or updated ebuilds. It prevents missing files from
# being added to the list of redistributed ones when actually they have no
# counterpart on the filesystem.
#
# Such a list can be found in "everything.sums.gentoo" file, which will
# tell to us whether an entry is OK, failed to open or read it
# (i.e., "FAILED") or hash computing did NOT match as expected. This way
# you can ensure that there will not be differences across source and
# binary releases.
#

# Change working directory to user home directory
cd ~
rm -f checksums.gentoo
rm -f checksums.txt.gentoo
rm -f everything.sums.gentoo

for category in `ls -1 /var/db/pkg/`; do
	for package in `ls -1 /var/db/pkg/$category`; do
		echo -e "\033[01;36m/var/db/pkg/$category/$package:\033[00m"
		grep "^obj" /var/db/pkg/$category/$package/CONTENTS | cut -d ' ' -f 2,3 >> checksums.gentoo
		cat checksums.gentoo | sed -e 's,\(^/.*\)* \([0-9a-f]*$\),\2  \1,g' >> checksums.txt.gentoo
		md5sum -c checksums.txt.gentoo 2>&1 >> everything.sums.gentoo
		rm checksums.gentoo checksums.txt.gentoo
	done
done
