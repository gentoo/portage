# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import io
import time
import portage
from portage import os_unicode_fs
from portage.data import secpass
from portage.output import xtermTitle

# We disable emergelog by default, since it's called from
# dblink.merge() and we don't want that to trigger log writes
# unless it's really called via emerge.
_disable = True
_emerge_log_dir = "/var/log"


def emergelog(xterm_titles, mystr, short_msg=None):

    if _disable:
        return

    if xterm_titles and short_msg:
        if "HOSTNAME" in os_unicode_fs.environ:
            short_msg = os_unicode_fs.environ["HOSTNAME"] + ": " + short_msg
        xtermTitle(short_msg)
    try:
        file_path = os_unicode_fs.path.join(_emerge_log_dir, "emerge.log")
        existing_log = os_unicode_fs.path.exists(file_path)
        mylogfile = io.open(
            file_path.encode(encoding="utf-8", errors="strict"),
            mode="a",
            encoding="utf-8",
            errors="backslashreplace",
        )
        if not existing_log:
            portage.util.apply_secpass_permissions(
                file_path, uid=portage.portage_uid, gid=portage.portage_gid, mode=0o660
            )
        mylock = portage.locks.lockfile(file_path)
        try:
            mylogfile.write("%.0f: %s\n" % (time.time(), mystr))
            mylogfile.close()
        finally:
            portage.locks.unlockfile(mylock)
    except (IOError, OSError, portage.exception.PortageException) as e:
        if secpass >= 1:
            portage.util.writemsg("emergelog(): %s\n" % (e,), noiselevel=-1)
