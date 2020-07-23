# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
import time
import portage
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.data import secpass
from portage.output import xtermTitle

# We disable emergelog by default, since it's called from
# dblink.merge() and we don't want that to trigger log writes
# unless it's really called via emerge.
_disable = True
_emerge_log_dir = '/var/log'

def emergelog(xterm_titles, mystr, short_msg=None):

	if _disable:
		return

	mystr = _unicode_decode(mystr)

	if short_msg is not None:
		short_msg = _unicode_decode(short_msg)

	if xterm_titles and short_msg:
		if "HOSTNAME" in os.environ:
			short_msg = os.environ["HOSTNAME"]+": "+short_msg
		xtermTitle(short_msg)
	try:
		file_path = os.path.join(_emerge_log_dir, 'emerge.log')
		existing_log = os.path.exists(file_path)
		mylogfile = io.open(_unicode_encode(file_path,
			encoding=_encodings['fs'], errors='strict'),
			mode='a', encoding=_encodings['content'],
			errors='backslashreplace')
		if not existing_log:
			portage.util.apply_secpass_permissions(file_path,
				uid=portage.portage_uid, gid=portage.portage_gid,
				mode=0o660)
		mylock = portage.locks.lockfile(file_path)
		try:
			mylogfile.write("%.0f: %s\n" % (time.time(), mystr))
			mylogfile.close()
		finally:
			portage.locks.unlockfile(mylock)
	except (IOError,OSError,portage.exception.PortageException) as e:
		if secpass >= 1:
			portage.util.writemsg("emergelog(): %s\n" % (e,), noiselevel=-1)
