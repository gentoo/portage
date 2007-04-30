# elog/mod_echo.py - elog dispatch module
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.output import EOutput
from portage.const import EBUILD_PHASES

_items = {}
def process(mysettings, cpv, logentries, fulltext):
	_items[cpv] = logentries

def finalize(mysettings):
	printer = EOutput()
	for cpv in _items.keys():
		print
		printer.einfo("Messages for package %s:" % cpv)
		print
		for phase in EBUILD_PHASES:
			if not phase in _items[cpv]:
				continue
			for msgtype, msgcontent in _items[cpv][phase]:
				fmap = {"INFO": printer.einfo,
						"WARN": printer.ewarn,
						"ERROR": printer.eerror,
						"LOG": printer.einfo,
						"QA": printer.ewarn}
				for line in msgcontent:
					fmap[msgtype](line.strip("\n"))
	return
