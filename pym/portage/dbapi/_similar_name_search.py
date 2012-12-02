# Copyright 2011-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import difflib

from portage.versions import catsplit

def similar_name_search(dbs, atom):

	cp_lower = atom.cp.lower()
	cat, pkg = catsplit(cp_lower)
	if cat == "null":
		cat = None

	all_cp = set()
	for db in dbs:
		all_cp.update(db.cp_all())

	# discard dir containing no ebuilds
	all_cp.discard(atom.cp)

	orig_cp_map = {}
	for cp_orig in all_cp:
		orig_cp_map.setdefault(cp_orig.lower(), []).append(cp_orig)
	all_cp = set(orig_cp_map)

	if cat:
		matches = difflib.get_close_matches(cp_lower, all_cp)
	else:
		pkg_to_cp = {}
		for other_cp in list(all_cp):
			other_pkg = catsplit(other_cp)[1]
			if other_pkg == pkg:
				# Check for non-identical package that
				# differs only by upper/lower case.
				identical = True
				for cp_orig in orig_cp_map[other_cp]:
					if catsplit(cp_orig)[1] != \
						catsplit(atom.cp)[1]:
						identical = False
						break
				if identical:
					# discard dir containing no ebuilds
					all_cp.discard(other_cp)
					continue
			pkg_to_cp.setdefault(other_pkg, set()).add(other_cp)

		pkg_matches = difflib.get_close_matches(pkg, pkg_to_cp)
		matches = []
		for pkg_match in pkg_matches:
			matches.extend(pkg_to_cp[pkg_match])

	matches_orig_case = []
	for cp in matches:
		matches_orig_case.extend(orig_cp_map[cp])

	return matches_orig_case
