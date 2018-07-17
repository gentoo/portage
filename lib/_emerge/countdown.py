# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import sys
import time

from portage.output import colorize


def countdown(secs=5, doing='Starting'):
	if secs:
		print(
			'>>> Waiting %s seconds before starting...\n'
			'>>> (Control-C to abort)...\n'
			'%s in:' % (secs, doing), end='')
		for sec in range(secs, 0, -1):
			sys.stdout.write(colorize('UNMERGE_WARN', ' %i' % sec))
			sys.stdout.flush()
			time.sleep(1)
		print()
