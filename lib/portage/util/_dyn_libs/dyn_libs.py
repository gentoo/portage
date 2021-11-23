# Copyright 2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os


def installed_dynlibs(directory):
    for _dirpath, _dirnames, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith(".so"):
                return True
    return False


def check_dyn_libs_inconsistent(directory, provides):
    """Checks directory for whether any dynamic libraries were installed and
    if PROVIDES corresponds."""

    # Let's check if we've got inconsistent results.
    # If we're installing dynamic libraries (.so files), we should
    # really have a PROVIDES.
    # (This is a complementary check at the point of ingestion for the
    # creation check in doebuild.py)
    # Note: we could check a non-empty PROVIDES against the list of .sos,
    # but this doesn't gain us anything. We're interested in failure
    # to properly parse the installed files at all, which should really
    # be a global problem (e.g. bug #811462)
    return not provides and installed_dynlibs(directory)
