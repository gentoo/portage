import portage.elog_modules.mod_save, portage.process, portage.exception

def process(mysettings, cpv, logentries, fulltext):
	elogfilename = portage.elog_modules.mod_save.process(mysettings, cpv, logentries, fulltext)
	
	if (not "PORTAGE_ELOG_COMMAND" in mysettings.keys()) \
			or len(mysettings["PORTAGE_ELOG_COMMAND"]) == 0:
		raise portage.exception.MissingParameter("!!! Custom logging requested but PORTAGE_ELOG_COMMAND is not defined")
	else:
		mylogcmd = mysettings["PORTAGE_ELOG_COMMAND"]
		mylogcmd = mylogcmd.replace("${LOGFILE}", elogfilename)
		mylogcmd = mylogcmd.replace("${PACKAGE}", cpv)
		retval = portage.process.spawn_bash(mylogcmd)
		if retval != 0:
			raise portage.exception.PortageException("!!! PORTAGE_ELOG_COMMAND failed with exitcode %d" % retval)
	return
