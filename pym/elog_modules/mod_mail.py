# portage.py -- core Portage functionality
# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage_mail, socket
from portage_exception import PortageException
from portage_util import writemsg

def process(mysettings, cpv, logentries, fulltext):
	if mysettings.has_key("PORTAGE_ELOG_MAILURI"):
		myrecipient = mysettings["PORTAGE_ELOG_MAILURI"].split()[0]
	else:
		myrecipient = "root@localhost"
	
	myfrom = mysettings["PORTAGE_ELOG_MAILFROM"]
	myfrom = myfrom.replace("${HOST}", socket.getfqdn())
	mysubject = mysettings["PORTAGE_ELOG_MAILSUBJECT"]
	mysubject = mysubject.replace("${PACKAGE}", cpv)
	mysubject = mysubject.replace("${HOST}", socket.getfqdn())

	mymessage = portage_mail.create_message(myfrom, myrecipient, mysubject, fulltext)
	try:
		portage_mail.send_mail(mysettings, mymessage)
	except PortageException, e:
		writemsg("%s\n" % str(e), noiselevel=-1)

	return
