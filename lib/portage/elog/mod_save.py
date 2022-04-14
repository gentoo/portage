# elog/mod_save.py - elog dispatch module
# Copyright 2006-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import io
import time
import portage
from portage import os_unicode_fs
from portage.data import portage_gid, portage_uid
from portage.package.ebuild.prepare_build_dirs import _ensure_log_subdirs
from portage.util import apply_permissions, ensure_dirs, normalize_path


def process(mysettings, key, logentries, fulltext):

    if mysettings.get("PORTAGE_LOGDIR"):
        logdir = normalize_path(mysettings["PORTAGE_LOGDIR"])
    else:
        logdir = os_unicode_fs.path.join(
            os_unicode_fs.sep,
            mysettings["EPREFIX"].lstrip(os_unicode_fs.sep),
            "var",
            "log",
            "portage",
        )

    if not os_unicode_fs.path.isdir(logdir):
        # Only initialize group/mode if the directory doesn't
        # exist, so that we don't override permissions if they
        # were previously set by the administrator.
        # NOTE: These permissions should be compatible with our
        # default logrotate config as discussed in bug 374287.
        uid = -1
        if portage.data.secpass >= 2:
            uid = portage_uid
        ensure_dirs(logdir, uid=uid, gid=portage_gid, mode=0o2770)

    cat, pf = portage.catsplit(key)

    elogfilename = (
        pf + ":" + time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time())) + ".log"
    )

    if "split-elog" in mysettings.features:
        log_subdir = os_unicode_fs.path.join(logdir, "elog", cat)
        elogfilename = os_unicode_fs.path.join(log_subdir, elogfilename)
    else:
        log_subdir = os_unicode_fs.path.join(logdir, "elog")
        elogfilename = os_unicode_fs.path.join(log_subdir, cat + ":" + elogfilename)
    _ensure_log_subdirs(logdir, log_subdir)

    try:
        with io.open(
            elogfilename.encode(encoding="utf-8", errors="strict"),
            mode="w",
            encoding="utf-8",
            errors="backslashreplace",
        ) as elogfile:
            elogfile.write(fulltext)
    except IOError as e:
        func_call = "open('%s', 'w')" % elogfilename
        if e.errno == errno.EACCES:
            raise portage.exception.PermissionDenied(func_call)
        elif e.errno == errno.EPERM:
            raise portage.exception.OperationNotPermitted(func_call)
        elif e.errno == errno.EROFS:
            raise portage.exception.ReadOnlyFileSystem(func_call)
        else:
            raise

    # Copy group permission bits from parent directory.
    elogdir_st = os_unicode_fs.stat(log_subdir)
    elogdir_gid = elogdir_st.st_gid
    elogdir_grp_mode = 0o060 & elogdir_st.st_mode

    # Copy the uid from the parent directory if we have privileges
    # to do so, for compatibility with our default logrotate
    # config (see bug 378451). With the "su portage portage"
    # directive and logrotate-3.8.0, logrotate's chown call during
    # the compression phase will only succeed if the log file's uid
    # is portage_uid.
    logfile_uid = -1
    if portage.data.secpass >= 2:
        logfile_uid = elogdir_st.st_uid
    apply_permissions(
        elogfilename, uid=logfile_uid, gid=elogdir_gid, mode=elogdir_grp_mode, mask=0
    )

    return elogfilename
