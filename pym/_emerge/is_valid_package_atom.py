# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import re
import portage

def is_valid_package_atom(x):
	if "/" not in x:
		alphanum = re.search(r'\w', x)
		if alphanum:
			x = x[:alphanum.start()] + "cat/" + x[alphanum.start():]
	return portage.isvalidatom(x, allow_blockers=False)
