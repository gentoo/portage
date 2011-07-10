# elog/mod_save.py - elog dispatch module
# Copyright 2006-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
import time
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.data import portage_uid, portage_gid
from portage.util import ensure_dirs

def process(mysettings, key, logentries, fulltext):
	path = key.replace("/", ":")

	if mysettings["PORT_LOGDIR"] != "":
		elogdir = os.path.join(mysettings["PORT_LOGDIR"], "elog")
	else:
		elogdir = os.path.join(os.sep, "var", "log", "portage", "elog")
	ensure_dirs(elogdir, uid=portage_uid, gid=portage_gid, mode=0o2770)

	cat = mysettings['CATEGORY']
	pf = mysettings['PF']

	elogfilename = pf + ":" + _unicode_decode(
		time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time())),
		encoding=_encodings['content'], errors='replace') + ".log"

	if "split-elog" in mysettings.features:
		elogfilename = os.path.join(elogdir, cat, elogfilename)
	else:
		elogfilename = os.path.join(elogdir, cat + ':' + elogfilename)
	ensure_dirs(os.path.dirname(elogfilename),
		uid=portage_uid, gid=portage_gid, mode=0o2770)

	elogfile = io.open(_unicode_encode(elogfilename,
		encoding=_encodings['fs'], errors='strict'),
		mode='w', encoding=_encodings['content'], errors='backslashreplace')
	elogfile.write(_unicode_decode(fulltext))
	elogfile.close()

	return elogfilename
