# elog/mod_mail.py - elog dispatch module
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage.mail, socket
from portage.exception import PortageException
from portage.util import writemsg

def process(mysettings, key, logentries, fulltext):
	if "PORTAGE_ELOG_MAILURI" in mysettings:
		myrecipient = mysettings["PORTAGE_ELOG_MAILURI"].split()[0]
	else:
		myrecipient = "root@localhost"
	
	myfrom = mysettings["PORTAGE_ELOG_MAILFROM"]
	myfrom = myfrom.replace("${HOST}", socket.getfqdn())
	mysubject = mysettings["PORTAGE_ELOG_MAILSUBJECT"]
	mysubject = mysubject.replace("${PACKAGE}", key)
	mysubject = mysubject.replace("${HOST}", socket.getfqdn())

	# look at the phases listed in our logentries to figure out what action was performed
	action = "merged"
	for phase in logentries.keys():
		# if we found a *rm phase assume that the package was unmerged
		if phase in ["postrm", "prerm"]:
			action = "unmerged"
	# if we think that the package was unmerged, make sure there was no unexpected
	# phase recorded to avoid misinformation
	if action == "unmerged":
		for phase in logentries.keys():
			if phase not in ["postrm", "prerm", "other"]:
				action = "unknown"

	mysubject = mysubject.replace("${ACTION}", action)

	mymessage = portage.mail.create_message(myfrom, myrecipient, mysubject, fulltext)
	try:
		portage.mail.send_mail(mysettings, mymessage)
	except PortageException, e:
		writemsg("%s\n" % str(e), noiselevel=-1)

	return
