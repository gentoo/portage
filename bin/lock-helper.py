#!/usr/bin/python -b
# Copyright 2010-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os
import sys
sys.path.insert(0, os.environ['PORTAGE_PYM_PATH'])
import portage
portage._internal_caller = True
portage._disable_legacy_globals()

def main(args):

	if args and isinstance(args[0], bytes):
		for i, x in enumerate(args):
			args[i] = portage._unicode_decode(x, errors='strict')

	# Make locks quiet since unintended locking messages displayed on
	# stdout would corrupt the intended output of this program.
	portage.locks._quiet = True
	lock_obj = portage.locks.lockfile(args[0], wantnewlockfile=True)
	sys.stdout.write('\0')
	sys.stdout.flush()
	sys.stdin.read(1)
	portage.locks.unlockfile(lock_obj)
	return portage.os.EX_OK

if __name__ == "__main__":
	rval = main(sys.argv[1:])
	sys.exit(rval)
