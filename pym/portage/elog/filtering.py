# elog/messages.py - elog core functions
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.const import EBUILD_PHASES

def filter_loglevels(logentries, loglevels):
	# remove unwanted entries from all logentries
	rValue = {}
	loglevels = [x.upper() for x in loglevels]
	for phase in logentries:
		for msgtype, msgcontent in logentries[phase]:
			if msgtype.upper() in loglevels or "*" in loglevels:
				if phase not in rValue:
					rValue[phase] = []
				rValue[phase].append((msgtype, msgcontent))
	return rValue
