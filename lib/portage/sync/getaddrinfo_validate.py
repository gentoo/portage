# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import sys

if sys.hexversion >= 0x3000000:
	basestring = str

def getaddrinfo_validate(addrinfos):
	"""
	Validate structures returned from getaddrinfo(),
	since they may be corrupt, especially when python
	has IPv6 support disabled (bug #340899).
	"""
	valid_addrinfos = []
	for addrinfo in addrinfos:
		try:
			if len(addrinfo) != 5:
				continue
			if len(addrinfo[4]) < 2:
				continue
			if not isinstance(addrinfo[4][0], basestring):
				continue
		except TypeError:
			continue

		valid_addrinfos.append(addrinfo)

	return valid_addrinfos
