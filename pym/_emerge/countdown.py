# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import sys
import time

from portage.output import colorize

def countdown(secs=5, doing="Starting"):
	if secs:
		print(">>> Waiting",secs,"seconds before starting...")
		print(">>> (Control-C to abort)...\n"+doing+" in: ", end=' ')
		ticks=list(range(secs))
		ticks.reverse()
		for sec in ticks:
			sys.stdout.write(colorize("UNMERGE_WARN", str(sec+1)+" "))
			sys.stdout.flush()
			time.sleep(1)
		print()

