import smtplib, email.Message, socket, portage_exception

def process(mysettings, cpv, logentries, fulltext):
	mymailhost = "localhost"
	mymailport = 25
	mymailuser = ""
	mymailpasswd = ""
	myrecipient = "root@localhost"
	
	# Syntax for PORTAGE_LOG_MAILURI (if defined):
	# adress [[user:passwd@]mailserver[:port]]
	# where adress:     recipient adress
	#       user:       username for smtp auth (defaults to none)
	#       passwd:     password for smtp auth (defaults to none)
	#       mailserver: smtp server that should be used to deliver the mail (defaults to localhost)
	#       port:       port to use on the given smtp server (defaults to 25, values > 100000 indicate that starttls should be used on (port-100000))
	if " " in mysettings["PORTAGE_ELOG_MAILURI"]:
		myrecipient, mymailuri = mysettings["PORTAGE_ELOG_MAILURI"].split()
		if "@" in mymailuri:
			myauthdata, myconndata = mymailuri.rsplit("@", 1)
			try:
				mymailuser,mymailpasswd = myauthdata.split(":")
			except ValueError:
				print "!!! invalid SMTP AUTH configuration, trying unauthenticated ..."
		else:
			myconndata = mymailuri
		if ":" in myconndata:
			mymailhost,mymailport = myconndata.split(":")
		else:
			mymailhost = myconndata
	else:
		myrecipient = mysettings["PORTAGE_ELOG_MAILURI"]
	try:
		myfrom = mysettings["PORTAGE_ELOG_MAILFROM"]
		
		mymessage = email.Message.Message()
		mymessage.set_unixfrom(myfrom)
		mymessage.set_payload(fulltext)
		mymessage["To"] = myrecipient
		mymessage["From"] = myfrom
		
		mysubject = mysettings["PORTAGE_ELOG_MAILSUBJECT"]
		mysubject = mysubject.replace("${PACKAGE}", cpv)
		mysubject = mysubject.replace("${HOST}", socket.getfqdn())
		
		mymessage["Subject"] = mysubject
				
		if int(mymailport) > 100000:
			myconn = smtplib.SMTP(mymailhost, int(mymailport) - 100000)
			myconn.starttls()
		else:
			myconn = smtplib.SMTP(mymailhost, mymailport)
		if mymailuser != "" and mymailpasswd != "":
			myconn.login(mymailuser, mymailpasswd)
		myconn.sendmail(myfrom, myrecipient, mymessage.as_string())
		myconn.quit()
	except smtplib.SMTPException, e:
		raise portage_exception.PortageException("!!! An error occured while trying to send logmail:\n"+str(e))
	except socket.error, e:
		raise portage_exception.PortageException("!!! A network error occured while trying to send logmail:\n"+str(e)+"\nSure you configured PORTAGE_ELOG_MAILURI correctly?")
	return
