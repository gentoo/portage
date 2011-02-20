# portage.py -- core Portage functionality
# Copyright 1998-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# Since python ebuilds remove the 'email' module when USE=build
# is enabled, use a local import so that
# portage.proxy.lazyimport._preload_portage_submodules()
# can load this module even though the 'email' module is missing.
# The elog mail modules won't work, but at least an ImportError
# won't cause portage to crash during stage builds. Since the
# 'smtlib' module imports the 'email' module, that's imported
# locally as well.

import socket
import sys
import time

from portage import os
from portage import _encodings
from portage import _unicode_decode, _unicode_encode
from portage.localization import _
import portage

if sys.hexversion >= 0x3000000:
	basestring = str

	def _force_ascii_if_necessary(s):
		# Force ascii encoding in order to avoid UnicodeEncodeError
		# from smtplib.sendmail with python3 (bug #291331).
		s = _unicode_encode(s,
			encoding='ascii', errors='backslashreplace')
		s = _unicode_decode(s,
			encoding='ascii', errors='replace')
		return s

else:

	def _force_ascii_if_necessary(s):
		return s

def TextMessage(_text):
	from email.mime.text import MIMEText
	mimetext = MIMEText(_text)
	if sys.hexversion >= 0x3000000:
		mimetext.set_charset("UTF-8")
	return mimetext

def create_message(sender, recipient, subject, body, attachments=None):

	from email.header import Header
	from email.mime.base import MIMEBase as BaseMessage
	from email.mime.multipart import MIMEMultipart as MultipartMessage

	if sys.hexversion < 0x3000000:
		sender = _unicode_encode(sender,
			encoding=_encodings['content'], errors='strict')
		recipient = _unicode_encode(recipient,
			encoding=_encodings['content'], errors='strict')
		subject = _unicode_encode(subject,
			encoding=_encodings['content'], errors='backslashreplace')
		body = _unicode_encode(body,
			encoding=_encodings['content'], errors='backslashreplace')

	if attachments == None:
		mymessage = TextMessage(body)
	else:
		mymessage = MultipartMessage()
		mymessage.attach(TextMessage(body))
		for x in attachments:
			if isinstance(x, BaseMessage):
				mymessage.attach(x)
			elif isinstance(x, basestring):
				if sys.hexversion < 0x3000000:
					x = _unicode_encode(x,
						encoding=_encodings['content'],
						errors='backslashreplace')
				mymessage.attach(TextMessage(x))
			else:
				raise portage.exception.PortageException(_("Can't handle type of attachment: %s") % type(x))

	mymessage.set_unixfrom(sender)
	mymessage["To"] = recipient
	mymessage["From"] = sender

	# Use Header as a workaround so that long subject lines are wrapped
	# correctly by <=python-2.6 (gentoo bug #263370, python issue #1974).
	# Also, need to force ascii for python3, in order to avoid
	# UnicodeEncodeError with non-ascii characters:
	#  File "/usr/lib/python3.1/email/header.py", line 189, in __init__
	#    self.append(s, charset, errors)
	#  File "/usr/lib/python3.1/email/header.py", line 262, in append
	#    input_bytes = s.encode(input_charset, errors)
	#UnicodeEncodeError: 'ascii' codec can't encode characters in position 0-9: ordinal not in range(128)
	mymessage["Subject"] = Header(_force_ascii_if_necessary(subject))
	mymessage["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S %z")
	
	return mymessage

def send_mail(mysettings, message):

	import smtplib

	mymailhost = "localhost"
	mymailport = 25
	mymailuser = ""
	mymailpasswd = ""
	myrecipient = "root@localhost"
	
	# Syntax for PORTAGE_ELOG_MAILURI (if defined):
	# adress [[user:passwd@]mailserver[:port]]
	# where adress:     recipient adress
	#       user:       username for smtp auth (defaults to none)
	#       passwd:     password for smtp auth (defaults to none)
	#       mailserver: smtp server that should be used to deliver the mail (defaults to localhost)
	#					alternatively this can also be the absolute path to a sendmail binary if you don't want to use smtp
	#       port:       port to use on the given smtp server (defaults to 25, values > 100000 indicate that starttls should be used on (port-100000))
	if " " in mysettings.get("PORTAGE_ELOG_MAILURI", ""):
		myrecipient, mymailuri = mysettings["PORTAGE_ELOG_MAILURI"].split()
		if "@" in mymailuri:
			myauthdata, myconndata = mymailuri.rsplit("@", 1)
			try:
				mymailuser,mymailpasswd = myauthdata.split(":")
			except ValueError:
				print(_("!!! invalid SMTP AUTH configuration, trying unauthenticated ..."))
		else:
			myconndata = mymailuri
		if ":" in myconndata:
			mymailhost,mymailport = myconndata.split(":")
		else:
			mymailhost = myconndata
	else:
		myrecipient = mysettings.get("PORTAGE_ELOG_MAILURI", "")
	
	myfrom = message.get("From")

	if sys.hexversion < 0x3000000:
		myrecipient = _unicode_encode(myrecipient,
			encoding=_encodings['content'], errors='strict')
		mymailhost = _unicode_encode(mymailhost,
			encoding=_encodings['content'], errors='strict')
		mymailport = _unicode_encode(mymailport,
			encoding=_encodings['content'], errors='strict')
		myfrom = _unicode_encode(myfrom,
			encoding=_encodings['content'], errors='strict')
		mymailuser = _unicode_encode(mymailuser,
			encoding=_encodings['content'], errors='strict')
		mymailpasswd = _unicode_encode(mymailpasswd,
			encoding=_encodings['content'], errors='strict')

	# user wants to use a sendmail binary instead of smtp
	if mymailhost[0] == os.sep and os.path.exists(mymailhost):
		fd = os.popen(mymailhost+" -f "+myfrom+" "+myrecipient, "w")
		fd.write(_force_ascii_if_necessary(message.as_string()))
		if fd.close() != None:
			sys.stderr.write(_("!!! %s returned with a non-zero exit code. This generally indicates an error.\n") % mymailhost)
	else:
		try:
			if int(mymailport) > 100000:
				myconn = smtplib.SMTP(mymailhost, int(mymailport) - 100000)
				myconn.ehlo()
				if not myconn.has_extn("STARTTLS"):
					raise portage.exception.PortageException(_("!!! TLS support requested for logmail but not suported by server"))
				myconn.starttls()
				myconn.ehlo()
			else:
				myconn = smtplib.SMTP(mymailhost, mymailport)
			if mymailuser != "" and mymailpasswd != "":
				myconn.login(mymailuser, mymailpasswd)

			message_str = _force_ascii_if_necessary(message.as_string())
			myconn.sendmail(myfrom, myrecipient, message_str)
			myconn.quit()
		except smtplib.SMTPException as e:
			raise portage.exception.PortageException(_("!!! An error occured while trying to send logmail:\n")+str(e))
		except socket.error as e:
			raise portage.exception.PortageException(_("!!! A network error occured while trying to send logmail:\n%s\nSure you configured PORTAGE_ELOG_MAILURI correctly?") % str(e))
	return
	
