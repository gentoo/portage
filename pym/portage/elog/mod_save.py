# elog/mod_save.py - elog dispatch module
# Copyright 2006-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os, time
from portage.data import portage_uid, portage_gid
from portage.util import ensure_dirs
from portage.const import EPREFIX

def process(mysettings, key, logentries, fulltext):
	path = key.replace("/", ":")

	if mysettings["PORT_LOGDIR"] != "":
		elogdir = os.path.join(mysettings["PORT_LOGDIR"], "elog")
	else:
		elogdir = os.path.join(EPREFIX, "var", "log", "portage", "elog")
	ensure_dirs(elogdir, uid=portage_uid, gid=portage_gid, mode=02770)

	elogfilename = elogdir+"/"+path+":"+time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time()))+".log"
	elogfile = open(elogfilename, "w")
	elogfile.write(fulltext)
	elogfile.close()

	return elogfilename
