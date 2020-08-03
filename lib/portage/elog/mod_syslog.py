# elog/mod_syslog.py - elog dispatch module
# Copyright 2006-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import syslog
from portage.const import EBUILD_PHASES

_pri = {
	"INFO"   : syslog.LOG_INFO,
	"WARN"   : syslog.LOG_WARNING,
	"ERROR"  : syslog.LOG_ERR,
	"LOG"    : syslog.LOG_NOTICE,
	"QA"     : syslog.LOG_WARNING
}

def process(mysettings, key, logentries, fulltext):
	syslog.openlog("portage", syslog.LOG_ERR | syslog.LOG_WARNING | syslog.LOG_INFO | syslog.LOG_NOTICE, syslog.LOG_LOCAL5)
	for phase in EBUILD_PHASES:
		if not phase in logentries:
			continue
		for msgtype, msgcontent in logentries[phase]:
			if isinstance(msgcontent, str):
				msgcontent = [msgcontent]
			for line in msgcontent:
				line = "%s: %s: %s" % (key, phase, line)
				syslog.syslog(_pri[msgtype], line.rstrip("\n"))
	syslog.closelog()
