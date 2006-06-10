# archive_conf.py -- functionality common to archive-conf and dispatch-conf
# Copyright 2003-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


# Library by Wayne Davison <gentoo@blorf.net>, derived from code
# written by Jeremy Wohl (http://igmus.org)

from stat import *
import os, sys, commands, shutil

sys.path = ["/usr/lib/portage/pym"]+sys.path
import portage

RCS_BRANCH = '1.1.1'
RCS_LOCK = 'rcs -ko -M -l'
RCS_PUT = 'ci -t-"Archived config file." -m"dispatch-conf update."'
RCS_GET = 'co'
RCS_MERGE = 'rcsmerge -p -r' + RCS_BRANCH + ' %s >%s'

DIFF3_MERGE = 'diff3 -mE %s %s %s >%s'

def read_config(mandatory_opts):
    try:
        opts = portage.getconfig('/etc/dispatch-conf.conf')
    except:
        opts = None

    if not opts:
        print >> sys.stderr, 'dispatch-conf: Error reading /etc/dispatch-conf.conf; fatal'
        sys.exit(1)

    for key in mandatory_opts:
        if not opts.has_key(key):
            if key == "merge":
                opts["merge"] = "sdiff --suppress-common-lines --output=%s %s %s"
            else:
                print >> sys.stderr, 'dispatch-conf: Missing option "%s" in /etc/dispatch-conf.conf; fatal' % (key,)

    if not os.path.exists(opts['archive-dir']):
        os.mkdir(opts['archive-dir'])
    elif not os.path.isdir(opts['archive-dir']):
        print >> sys.stderr, 'dispatch-conf: Config archive dir [%s] must exist; fatal' % (opts['archive-dir'],)
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
    except:
        pass

    try:
        shutil.copy2(curconf, archive)
    except(IOError, os.error), why:
        print >> sys.stderr, 'dispatch-conf: Error copying %s to %s: %s; fatal' % \
              (curconf, archive, str(why))
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
        except(IOError, os.error), why:
            print >> sys.stderr, 'dispatch-conf: Error copying %s to %s: %s; fatal' % \
                  (newconf, archive, str(why))

        if has_branch:
            if mrgconf != '':
                # This puts the results of the merge into mrgconf.
                ret = os.system(RCS_MERGE % (archive, mrgconf))
                mystat = os.lstat(newconf)
                os.chmod(mrgconf, mystat[ST_MODE])
                os.chown(mrgconf, mystat[ST_UID], mystat[ST_GID])
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
    except:
        pass

    # Archive the current config file if it isn't already saved
    if os.path.exists(archive) \
     and len(commands.getoutput('diff -aq %s %s' % (curconf,archive))) != 0:
        suf = 1
        while suf < 9 and os.path.exists(archive + '.' + str(suf)):
            suf += 1

        while suf > 1:
            os.rename(archive + '.' + str(suf-1), archive + '.' + str(suf))
            suf -= 1

        os.rename(archive, archive + '.1')

    try:
        shutil.copy2(curconf, archive)
    except(IOError, os.error), why:
        print >> sys.stderr, 'dispatch-conf: Error copying %s to %s: %s; fatal' % \
              (curconf, archive, str(why))

    if newconf != '':
        # Save off new config file in the archive dir with .dist.new suffix
        try:
            shutil.copy2(newconf, archive + '.dist.new')
        except(IOError, os.error), why:
            print >> sys.stderr, 'dispatch-conf: Error copying %s to %s: %s; fatal' % \
                  (newconf, archive + '.dist.new', str(why))

        ret = 0
        if mrgconf != '' and os.path.exists(archive + '.dist'):
            # This puts the results of the merge into mrgconf.
            ret = os.system(DIFF3_MERGE % (curconf, archive + '.dist', newconf, mrgconf))
            mystat = os.lstat(newconf)
            os.chmod(mrgconf, mystat[ST_MODE])
            os.chown(mrgconf, mystat[ST_UID], mystat[ST_GID])

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
