# elog/mod_echo.py - elog dispatch module
# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys
from portage.output import EOutput, colorize
from portage.const import EBUILD_PHASES
from portage.localization import _


_items = []
def process(mysettings, key, logentries, fulltext):
	global _items
	logfile = None
	# output logfile explicitly only if it isn't in tempdir, otherwise
	# it will be removed anyway
	if (key == mysettings.mycpv and
		"PORTAGE_LOGDIR" in mysettings and
		"PORTAGE_LOG_FILE" in mysettings):
		logfile = mysettings["PORTAGE_LOG_FILE"]
	_items.append((mysettings["ROOT"], key, logentries, logfile))

def finalize():
	# For consistency, send all message types to stdout.
	sys.stdout.flush()
	sys.stderr.flush()
	stderr = sys.stderr
	try:
		sys.stderr = sys.stdout
		_finalize()
	finally:
		sys.stderr = stderr
		sys.stdout.flush()
		sys.stderr.flush()

def _finalize():
	global _items
	printer = EOutput()
	for root, key, logentries, logfile in _items:
		print()
		if root == "/":
			printer.einfo(_("Messages for package %s:") %
				colorize("INFORM", key))
		else:
			printer.einfo(_("Messages for package %(pkg)s merged to %(root)s:") %
				{"pkg": colorize("INFORM", key), "root": root})
		if logfile is not None:
			printer.einfo(_("Log file: %s") % colorize("INFORM", logfile))
		print()
		for phase in EBUILD_PHASES:
			if phase not in logentries:
				continue
			for msgtype, msgcontent in logentries[phase]:
				fmap = {"INFO": printer.einfo,
						"WARN": printer.ewarn,
						"ERROR": printer.eerror,
						"LOG": printer.einfo,
						"QA": printer.ewarn}
				if isinstance(msgcontent, str):
					msgcontent = [msgcontent]
				for line in msgcontent:
					fmap[msgtype](line.strip("\n"))
	_items = []
