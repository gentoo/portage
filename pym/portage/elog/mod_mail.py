# elog/mod_mail.py - elog dispatch module
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import portage.mail, socket

def process(mysettings, cpv, logentries, fulltext):
	if mysettings.has_key("PORTAGE_ELOG_MAILURI"):
		myrecipient = mysettings["PORTAGE_ELOG_MAILURI"].split()[0]
	else:
		myrecipient = "root@localhost"
	
	myfrom = mysettings["PORTAGE_ELOG_MAILFROM"]
	mysubject = mysettings["PORTAGE_ELOG_MAILSUBJECT"]
	mysubject = mysubject.replace("${PACKAGE}", cpv)
	mysubject = mysubject.replace("${HOST}", socket.getfqdn())

	mymessage = portage.mail.create_message(myfrom, myrecipient, mysubject, fulltext)
	portage.mail.send_mail(mysettings, mymessage)

	return
