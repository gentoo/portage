# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import re
from portage.dep import isvalidatom

def insert_category_into_atom(atom, category):
	# Handle '*' character for "extended syntax" wildcard support.
	alphanum = re.search(r'[\*\w]', atom, re.UNICODE)
	if alphanum:
		ret = atom[:alphanum.start()] + "%s/" % category + \
			atom[alphanum.start():]
	else:
		ret = None
	return ret

def is_valid_package_atom(x, allow_repo=False, allow_build_id=True):
	if "/" not in x.split(":")[0]:
		x2 = insert_category_into_atom(x, 'cat')
		if x2 != None:
			x = x2
	return isvalidatom(x, allow_blockers=False, allow_repo=allow_repo,
		allow_build_id=allow_build_id)
