# elog/mod_save.py - elog dispatch module
# Copyright 2006-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
import time
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.data import portage_gid, portage_uid
from portage.package.ebuild.prepare_build_dirs import _ensure_log_subdirs
from portage.util import ensure_dirs, normalize_path

def process(mysettings, key, logentries, fulltext):

	if mysettings.get("PORT_LOGDIR"):
		logdir = normalize_path(mysettings["PORT_LOGDIR"])
	else:
		logdir = os.path.join(os.sep, "var", "log", "portage")

	if not os.path.isdir(logdir):
		# Only initialize group/mode if the directory doesn't
		# exist, so that we don't override permissions if they
		# were previously set by the administrator.
		# NOTE: These permissions should be compatible with our
		# default logrotate config as discussed in bug 374287.
		ensure_dirs(logdir, uid=portage_uid, gid=portage_gid, mode=0o2770)

	cat = mysettings['CATEGORY']
	pf = mysettings['PF']

	elogfilename = pf + ":" + _unicode_decode(
		time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time())),
		encoding=_encodings['content'], errors='replace') + ".log"

	if "split-elog" in mysettings.features:
		log_subdir = os.path.join(logdir, "elog", cat)
		elogfilename = os.path.join(log_subdir, elogfilename)
	else:
		log_subdir = os.path.join(logdir, "elog")
		elogfilename = os.path.join(log_subdir, cat + ':' + elogfilename)
	_ensure_log_subdirs(logdir, log_subdir)

	elogfile = io.open(_unicode_encode(elogfilename,
		encoding=_encodings['fs'], errors='strict'),
		mode='w', encoding=_encodings['content'], errors='backslashreplace')
	elogfile.write(_unicode_decode(fulltext))
	elogfile.close()

	return elogfilename
