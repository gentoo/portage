# Copyright 2010-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = ["dep_expand"]

import re

from portage.dbapi.cpv_expand import cpv_expand
from portage.dep import Atom, isvalidatom
from portage.exception import InvalidAtom
from portage.versions import catsplit

def dep_expand(mydep, mydb=None, use_cache=1, settings=None):
	'''
	@rtype: Atom
	'''
	orig_dep = mydep
	if isinstance(orig_dep, Atom):
		has_cat = True
	else:
		if not mydep:
			return mydep
		if mydep[0] == "*":
			mydep = mydep[1:]
			orig_dep = mydep
		has_cat = '/' in orig_dep.split(':')[0]
		if not has_cat:
			alphanum = re.search(r'\w', orig_dep)
			if alphanum:
				mydep = orig_dep[:alphanum.start()] + "null/" + \
					orig_dep[alphanum.start():]
		try:
			mydep = Atom(mydep, allow_repo=True)
		except InvalidAtom:
			# Missing '=' prefix is allowed for backward compatibility.
			if not isvalidatom("=" + mydep, allow_repo=True):
				raise
			mydep = Atom('=' + mydep, allow_repo=True)
			orig_dep = '=' + orig_dep
		if not has_cat:
			null_cat, pn = catsplit(mydep.cp)
			mydep = pn

	if has_cat:
		# Optimize most common cases to avoid calling cpv_expand.
		if not mydep.cp.startswith("virtual/"):
			return mydep
		if not hasattr(mydb, "cp_list") or \
			mydb.cp_list(mydep.cp):
			return mydep
		# Fallback to legacy cpv_expand for old-style PROVIDE virtuals.
		mydep = mydep.cp

	expanded = cpv_expand(mydep, mydb=mydb,
		use_cache=use_cache, settings=settings)
	return Atom(orig_dep.replace(mydep, expanded, 1), allow_repo=True)
