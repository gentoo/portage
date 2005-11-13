import syslog
from portage_const import EBUILD_PHASES

def process(mysettings, cpv, logentries, fulltext):
	syslog.openlog("portage", syslog.LOG_ERR | syslog.LOG_WARNING | syslog.LOG_INFO | syslog.LOG_NOTICE, syslog.LOG_LOCAL5)
	for phase in EBUILD_PHASES.split():
		if not phase in logentries:
			continue
		for msgtype,msgcontent in logentries[phase]:
			pri = {"INFO": syslog.LOG_INFO, "WARN": syslog.LOG_WARNING, "ERROR": syslog.LOG_ERR, "LOG": syslog.LOG_NOTICE}
			msgtext = "".join(msgcontent)
			syslog.syslog(pri[msgtype], "%s: %s: %s" % (cpv, phase, msgtext))
	syslog.closelog()
