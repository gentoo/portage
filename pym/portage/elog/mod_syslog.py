# elog/mod_syslog.py - elog dispatch module
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import syslog
from portage.const import EBUILD_PHASES

def process(mysettings, cpv, logentries, fulltext):
	syslog.openlog("portage", syslog.LOG_ERR | syslog.LOG_WARNING | syslog.LOG_INFO | syslog.LOG_NOTICE, syslog.LOG_LOCAL5)
	for phase in EBUILD_PHASES:
		if not phase in logentries:
			continue
		for msgtype,msgcontent in logentries[phase]:
			pri = {"INFO": syslog.LOG_INFO, 
				"WARN": syslog.LOG_WARNING, 
				"ERROR": syslog.LOG_ERR, 
				"LOG": syslog.LOG_NOTICE,
				"QA": syslog.LOG_WARNING}
			msgtext = "".join(msgcontent)
			syslog.syslog(pri[msgtype], "%s: %s: %s" % (cpv, phase, msgtext))
	syslog.closelog()
