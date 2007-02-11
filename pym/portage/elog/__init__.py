from portage.const import EBUILD_PHASES
from portage.exception import PortageException
from portage.process import atexit_register
from portage.util import writemsg

from portage import listdir

import os

_elog_atexit_handlers = []
def elog_process(cpv, mysettings):
	mylogfiles = listdir(mysettings["T"]+"/logging/")
	# shortcut for packages without any messages
	if len(mylogfiles) == 0:
		return
	# exploit listdir() file order so we process log entries in chronological order
	mylogfiles.reverse()
	all_logentries = {}
	for f in mylogfiles:
		msgfunction, msgtype = f.split(".")
		if msgfunction not in EBUILD_PHASES:
			writemsg("!!! can't process invalid log file: %s\n" % f,
				noiselevel=-1)
			continue
		if not msgfunction in all_logentries:
			all_logentries[msgfunction] = []
		msgcontent = open(mysettings["T"]+"/logging/"+f, "r").readlines()
		all_logentries[msgfunction].append((msgtype, msgcontent))

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
	
	my_elog_classes = set(mysettings.get("PORTAGE_ELOG_CLASSES", "").split())
	default_logentries = filter_loglevels(all_logentries, my_elog_classes)

	# in case the filters matched all messages and no module overrides exist
	if len(default_logentries) == 0 and (not ":" in mysettings.get("PORTAGE_ELOG_SYSTEM", "")):
		return

	def combine_logentries(logentries):
		# generate a single string with all log messages
		rValue = ""
		for phase in EBUILD_PHASES:
			if not phase in logentries:
				continue
			for msgtype, msgcontent in logentries[phase]:
				rValue += "%s: %s\n" % (msgtype, phase)
				for line in msgcontent:
					rValue += line
				rValue += "\n"
		return rValue
	
	default_fulllog = combine_logentries(default_logentries)

	# pass the processing to the individual modules
	logsystems = mysettings["PORTAGE_ELOG_SYSTEM"].split()
	for s in logsystems:
		# allow per module overrides of PORTAGE_ELOG_CLASSES
		if ":" in s:
			s, levels = s.split(":", 1)
			levels = levels.split(",")
			mod_logentries = filter_loglevels(all_logentries, levels)
			mod_fulllog = combine_logentries(mod_logentries)
		else:
			mod_logentries = default_logentries
			mod_fulllog = default_fulllog
		if len(mod_logentries) == 0:
			continue
		# - is nicer than _ for module names, so allow people to use it.
		s = s.replace("-", "_")
		try:
			# FIXME: ugly ad.hoc import code
			# TODO:  implement a common portage module loader
			logmodule = __import__("portage.elog.mod_"+s)
			m = getattr(logmodule, "mod_"+s)
			def timeout_handler(signum, frame):
				raise PortageException("Timeout in elog_process for system '%s'" % s)
			import signal
			signal.signal(signal.SIGALRM, timeout_handler)
			# Timeout after one minute (in case something like the mail
			# module gets hung).
			signal.alarm(60)
			try:
				m.process(mysettings, cpv, mod_logentries, mod_fulllog)
			finally:
				signal.alarm(0)
			if hasattr(m, "finalize") and not m.finalize in _elog_atexit_handlers:
				_elog_atexit_handlers.append(m.finalize)
				atexit_register(m.finalize, mysettings)
		except (ImportError, AttributeError), e:
			writemsg("!!! Error while importing logging modules " + \
				"while loading \"mod_%s\":\n" % str(s))
			writemsg("%s\n" % str(e), noiselevel=-1)
		except portage.exception.PortageException, e:
			writemsg("%s\n" % str(e), noiselevel=-1)

	# clean logfiles to avoid repetitions
	for f in mylogfiles:
		try:
			os.unlink(os.path.join(mysettings["T"], "logging", f))
		except OSError:
			pass
