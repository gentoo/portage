# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import re

# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
import portage

def is_valid_package_atom(x):
	if "/" not in x:
		alphanum = re.search(r'\w', x)
		if alphanum:
			x = x[:alphanum.start()] + "cat/" + x[alphanum.start():]
	return portage.isvalidatom(x)
