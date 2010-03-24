# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

if sys.hexversion >= 0x3000000:
	basestring = str

# formats a size given in bytes nicely
def format_size(mysize):
	if isinstance(mysize, basestring):
		return mysize
	if 0 != mysize % 1024:
		# Always round up to the next kB so that it doesn't show 0 kB when
		# some small file still needs to be fetched.
		mysize += 1024 - mysize % 1024
	mystr=str(mysize//1024)
	mycount=len(mystr)
	while (mycount > 3):
		mycount-=3
		mystr=mystr[:mycount]+","+mystr[mycount:]
	return mystr+" kB"

