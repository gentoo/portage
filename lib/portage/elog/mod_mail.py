# elog/mod_mail.py - elog dispatch module
# Copyright 2006-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage.mail
import socket

from portage.exception import PortageException
from portage.localization import _
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
	action = _("merged")
	for phase in logentries:
		# if we found a *rm phase assume that the package was unmerged
		if phase in ["postrm", "prerm"]:
			action = _("unmerged")
	# if we think that the package was unmerged, make sure there was no unexpected
	# phase recorded to avoid misinformation
	if action == _("unmerged"):
		for phase in logentries:
			if phase not in ["postrm", "prerm", "other"]:
				action = _("unknown")

	mysubject = mysubject.replace("${ACTION}", action)

	mymessage = portage.mail.create_message(myfrom, myrecipient, mysubject, fulltext)
	try:
		portage.mail.send_mail(mysettings, mymessage)
	except PortageException as e:
		writemsg("%s\n" % str(e), noiselevel=-1)
