# elog/mod_echo.py - elog dispatch module
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from portage.output import EOutput, colorize
from portage.const import EBUILD_PHASES

_items = []
def process(mysettings, key, logentries, fulltext):
	global _items
	_items.append((mysettings, key, logentries))

def finalize(mysettings=None):
	"""The mysettings parameter is just for backward compatibility since
	an older version of portage will import the module from a newer version
	when it upgrades itself."""
	global _items
	printer = EOutput()
	for mysettings, key, logentries in _items:
		root_msg = ""
		if mysettings["ROOT"] != "/":
			root_msg = " merged to %s" % mysettings["ROOT"]
		print
		printer.einfo("Messages for package %s%s:" % \
			(colorize("INFORM", key), root_msg))
		print
		for phase in EBUILD_PHASES:
			if phase not in logentries:
				continue
			for msgtype, msgcontent in logentries[phase]:
				fmap = {"INFO": printer.einfo,
						"WARN": printer.ewarn,
						"ERROR": printer.eerror,
						"LOG": printer.einfo,
						"QA": printer.ewarn,
						"BLANK": printer.eblank}
				if isinstance(msgcontent, basestring):
					msgcontent = [msgcontent]
				for line in msgcontent:
					fmap[msgtype](line.strip("\n"))
	_items = []
	return
