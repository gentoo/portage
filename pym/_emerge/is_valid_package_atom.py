# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import re
import portage
import _emerge.depgraph

def is_valid_package_atom(x, allow_repo=False):
	if "/" not in x:
		x2 = _emerge.depgraph.insert_category_into_atom(x, 'cat')
		if x2 != None:
			x = x2
	return portage.isvalidatom(x, allow_blockers=False, allow_repo=allow_repo)
