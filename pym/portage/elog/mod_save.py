# elog/mod_save.py - elog dispatch module
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os, time
from portage.data import portage_uid, portage_gid

def process(mysettings, key, logentries, fulltext):
	path = key.replace("/", ":")

	if mysettings["PORT_LOGDIR"] != "":
		elogdir = os.path.join(mysettings["PORT_LOGDIR"], "elog")
	else:
		elogdir = os.path.join(os.sep, "var", "log", "portage", "elog")
	if not os.path.exists(elogdir):
		os.makedirs(elogdir)
	os.chown(elogdir, portage_uid, portage_gid)
	os.chmod(elogdir, 02770)

	elogfilename = elogdir+"/"+path+":"+time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time()))+".log"
	elogfile = open(elogfilename, "w")
	elogfile.write(fulltext)
	elogfile.close()

	return elogfilename
