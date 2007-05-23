# elog/messages.py - elog core functions
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: __init__.py 6458 2007-04-30 02:31:30Z genone $

def filter_loglevels(logentries, loglevels):
	# remove unwanted entries from all logentries
	rValue = {}
	loglevels = map(str.upper, loglevels)
	for phase in logentries.keys():
		for msgtype, msgcontent in logentries[phase]:
			if msgtype.upper() in loglevels or "*" in loglevels:
				if not rValue.has_key(phase):
					rValue[phase] = []
				rValue[phase].append((msgtype, msgcontent))
	return rValue
	
