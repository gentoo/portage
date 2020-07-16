# -*- coding:utf-8 -*-

from __future__ import print_function

import sys


def warn(txt):
	print("repoman: " + txt)


def err(txt):
	warn(txt)
	sys.exit(1)


def caterror(catdir, repodir):
	err(
		"%s is not an official category."
		"  Skipping QA checks in this directory.\n"
		"Please ensure that you add %s to %s/profiles/categories\n"
		"if it is a new category." % (catdir, catdir, repodir))
