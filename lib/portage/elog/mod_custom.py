# elog/mod_custom.py - elog dispatch module
# Copyright 2006-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage.elog.mod_save
import portage.exception
import portage.process

def process(mysettings, key, logentries, fulltext):
	elogfilename = portage.elog.mod_save.process(mysettings, key, logentries, fulltext)

	if not mysettings.get("PORTAGE_ELOG_COMMAND"):
		raise portage.exception.MissingParameter("!!! Custom logging requested but PORTAGE_ELOG_COMMAND is not defined")
	else:
		mylogcmd = mysettings["PORTAGE_ELOG_COMMAND"]
		mylogcmd = mylogcmd.replace("${LOGFILE}", elogfilename)
		mylogcmd = mylogcmd.replace("${PACKAGE}", key)
		retval = portage.process.spawn_bash(mylogcmd)
		if retval != 0:
			raise portage.exception.PortageException("!!! PORTAGE_ELOG_COMMAND failed with exitcode %d" % retval)
