# archive_conf.py -- functionality common to archive-conf and dispatch-conf
# Copyright 2003-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2


# Library by Wayne Davison <gentoo@blorf.net>, derived from code
# written by Jeremy Wohl (http://igmus.org)

from __future__ import print_function

import os, shutil, subprocess, sys

import portage
from portage.env.loaders import KeyValuePairFileLoader
from portage.localization import _
from portage.util import shlex_split, varexpand

RCS_BRANCH = '1.1.1'
RCS_LOCK = 'rcs -ko -M -l'
RCS_PUT = 'ci -t-"Archived config file." -m"dispatch-conf update."'
RCS_GET = 'co'
RCS_MERGE = "rcsmerge -p -r" + RCS_BRANCH + " '%s' > '%s'"

DIFF3_MERGE = "diff3 -mE '%s' '%s' '%s' > '%s'"

def diffstatusoutput(cmd, file1, file2):
    """
    Execute the string cmd in a shell with getstatusoutput() and return a
    2-tuple (status, output).
    """
    # Use Popen to emulate getstatusoutput(), since getstatusoutput() may
    # raise a UnicodeDecodeError which makes the output inaccessible.
    args = shlex_split(cmd % (file1, file2))
    if sys.hexversion < 0x3000000 or sys.hexversion >= 0x3020000:
        # Python 3.1 does not support bytes in Popen args.
        args = [portage._unicode_encode(x, errors='strict') for x in args]
    proc = subprocess.Popen(args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = portage._unicode_decode(proc.communicate()[0])
    if output and output[-1] == "\n":
        # getstatusoutput strips one newline
        output = output[:-1]
    return (proc.wait(), output)

def read_config(mandatory_opts):
    eprefix = portage.const.EPREFIX
    config_path = os.path.join(eprefix or os.sep, "etc/dispatch-conf.conf")
    loader = KeyValuePairFileLoader(config_path, None)
    opts, errors = loader.load()
    if not opts:
        print(_('dispatch-conf: Error reading /etc/dispatch-conf.conf; fatal'), file=sys.stderr)
        sys.exit(1)

	# Handle quote removal here, since KeyValuePairFileLoader doesn't do that.
    quotes = "\"'"
    for k, v in opts.items():
        if v[:1] in quotes and v[:1] == v[-1:]:
            opts[k] = v[1:-1]

    for key in mandatory_opts:
        if key not in opts:
            if key == "merge":
                opts["merge"] = "sdiff --suppress-common-lines --output='%s' '%s' '%s'"
            else:
                print(_('dispatch-conf: Missing option "%s" in /etc/dispatch-conf.conf; fatal') % (key,), file=sys.stderr)

    # archive-dir supports ${EPREFIX} expansion, in order to avoid hardcoding
    variables = {"EPREFIX": eprefix}
    opts['archive-dir'] = varexpand(opts['archive-dir'], mydict=variables)

    if not os.path.exists(opts['archive-dir']):
        os.mkdir(opts['archive-dir'])
        # Use restrictive permissions by default, in order to protect
        # against vulnerabilities (like bug #315603 involving rcs).
        os.chmod(opts['archive-dir'], 0o700)
    elif not os.path.isdir(opts['archive-dir']):
        print(_('dispatch-conf: Config archive dir [%s] must exist; fatal') % (opts['archive-dir'],), file=sys.stderr)
        sys.exit(1)

    return opts


def rcs_archive(archive, curconf, newconf, mrgconf):
    """Archive existing config in rcs (on trunk). Then, if mrgconf is
    specified and an old branch version exists, merge the user's changes
    and the distributed changes and put the result into mrgconf.  Lastly,
    if newconf was specified, leave it in the archive dir with a .dist.new
    suffix along with the last 1.1.1 branch version with a .dist suffix."""

    try:
        os.makedirs(os.path.dirname(archive))
    except OSError:
        pass

    if os.path.isfile(curconf):
        try:
            shutil.copy2(curconf, archive)
        except(IOError, os.error) as why:
            print(_('dispatch-conf: Error copying %(curconf)s to %(archive)s: %(reason)s; fatal') % \
                {"curconf": curconf, "archive": archive, "reason": str(why)}, file=sys.stderr)

    if os.path.exists(archive + ',v'):
        os.system(RCS_LOCK + ' ' + archive)
    os.system(RCS_PUT + ' ' + archive)

    ret = 0
    if newconf != '':
        os.system(RCS_GET + ' -r' + RCS_BRANCH + ' ' + archive)
        has_branch = os.path.exists(archive)
        if has_branch:
            os.rename(archive, archive + '.dist')

        try:
            shutil.copy2(newconf, archive)
        except(IOError, os.error) as why:
            print(_('dispatch-conf: Error copying %(newconf)s to %(archive)s: %(reason)s; fatal') % \
                  {"newconf": newconf, "archive": archive, "reason": str(why)}, file=sys.stderr)

        if has_branch:
            if mrgconf != '':
                # This puts the results of the merge into mrgconf.
                ret = os.system(RCS_MERGE % (archive, mrgconf))
                mystat = os.lstat(newconf)
                os.chmod(mrgconf, mystat.st_mode)
                os.chown(mrgconf, mystat.st_uid, mystat.st_gid)
        os.rename(archive, archive + '.dist.new')
    return ret


def file_archive(archive, curconf, newconf, mrgconf):
    """Archive existing config to the archive-dir, bumping old versions
    out of the way into .# versions (log-rotate style). Then, if mrgconf
    was specified and there is a .dist version, merge the user's changes
    and the distributed changes and put the result into mrgconf.  Lastly,
    if newconf was specified, archive it as a .dist.new version (which
    gets moved to the .dist version at the end of the processing)."""

    try:
        os.makedirs(os.path.dirname(archive))
    except OSError:
        pass

    # Archive the current config file if it isn't already saved
    if os.path.exists(archive) \
     and len(diffstatusoutput("diff -aq '%s' '%s'", curconf, archive)[1]) != 0:
        suf = 1
        while suf < 9 and os.path.exists(archive + '.' + str(suf)):
            suf += 1

        while suf > 1:
            os.rename(archive + '.' + str(suf-1), archive + '.' + str(suf))
            suf -= 1

        os.rename(archive, archive + '.1')

    if os.path.isfile(curconf):
        try:
            shutil.copy2(curconf, archive)
        except(IOError, os.error) as why:
            print(_('dispatch-conf: Error copying %(curconf)s to %(archive)s: %(reason)s; fatal') % \
                {"curconf": curconf, "archive": archive, "reason": str(why)}, file=sys.stderr)

    if newconf != '':
        # Save off new config file in the archive dir with .dist.new suffix
        try:
            shutil.copy2(newconf, archive + '.dist.new')
        except(IOError, os.error) as why:
            print(_('dispatch-conf: Error copying %(newconf)s to %(archive)s: %(reason)s; fatal') % \
                  {"newconf": newconf, "archive": archive + '.dist.new', "reason": str(why)}, file=sys.stderr)

        ret = 0
        if mrgconf != '' and os.path.exists(archive + '.dist'):
            # This puts the results of the merge into mrgconf.
            ret = os.system(DIFF3_MERGE % (curconf, archive + '.dist', newconf, mrgconf))
            mystat = os.lstat(newconf)
            os.chmod(mrgconf, mystat.st_mode)
            os.chown(mrgconf, mystat.st_uid, mystat.st_gid)

        return ret


def rcs_archive_post_process(archive):
    """Check in the archive file with the .dist.new suffix on the branch
    and remove the one with the .dist suffix."""
    os.rename(archive + '.dist.new', archive)
    if os.path.exists(archive + '.dist'):
        # Commit the last-distributed version onto the branch.
        os.system(RCS_LOCK + RCS_BRANCH + ' ' + archive)
        os.system(RCS_PUT + ' -r' + RCS_BRANCH + ' ' + archive)
        os.unlink(archive + '.dist')
    else:
        # Forcefully commit the last-distributed version onto the branch.
        os.system(RCS_PUT + ' -f -r' + RCS_BRANCH + ' ' + archive)


def file_archive_post_process(archive):
    """Rename the archive file with the .dist.new suffix to a .dist suffix"""
    os.rename(archive + '.dist.new', archive + '.dist')
