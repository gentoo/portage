#!/usr/bin/env python
# Copyright 2010-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import locale
import os
import sys

if (
    sys.getfilesystemencoding() != "utf-8"
    or locale.getpreferredencoding(False) != "utf-8"
):
    os.environ["PYTHONUTF8"] = "1"
    os.execv(sys.executable, [sys.executable] + sys.argv)


def main(args):
    sys.path.insert(0, os.environ["PORTAGE_PYM_PATH"])
    import portage

    portage._internal_caller = True
    portage._disable_legacy_globals()

    if args and isinstance(args[0], bytes):
        for i, x in enumerate(args):
            args[i] = x.decode("utf-8", "strict")

    # Make locks quiet since unintended locking messages displayed on
    # stdout would corrupt the intended output of this program.
    portage.locks._quiet = True
    lock_obj = portage.locks.lockfile(args[0], wantnewlockfile=True)
    sys.stdout.write("\0")
    sys.stdout.flush()
    sys.stdin.read(1)
    portage.locks.unlockfile(lock_obj)
    return os.EX_OK


if __name__ == "__main__":
    rval = main(sys.argv[1:])
    sys.exit(rval)
