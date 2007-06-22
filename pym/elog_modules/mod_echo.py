# elog_modules/mod_echo.py - elog dispatch module
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from output import EOutput
from portage_const import EBUILD_PHASES

_items = {}
def process(mysettings, key, logentries, fulltext):
	global _items
	config_root = mysettings["PORTAGE_CONFIGROOT"]
	mysettings, items = _items.setdefault(config_root, (mysettings, {}))
	items[key] = logentries

def finalize():
	global _items
	for mysettings, items in _items.itervalues():
		_finalize(mysettings, items)
	_items.clear()

def _finalize(mysettings, items):
	printer = EOutput()
	root_msg = ""
	if mysettings["ROOT"] != "/":
		root_msg = " merged to %s" % mysettings["ROOT"]
	for key, logentries in items.iteritems():
		print
		printer.einfo("Messages for package %s%s:" % (key, root_msg))
		print
		for phase in EBUILD_PHASES:
			if phase not in logentries:
				continue
			for msgtype, msgcontent in logentries[phase]:
				fmap = {"INFO": printer.einfo,
						"WARN": printer.ewarn,
						"ERROR": printer.eerror,
						"LOG": printer.einfo,
						"QA": printer.ewarn}
				for line in msgcontent:
					fmap[msgtype](line.strip("\n"))
	return
