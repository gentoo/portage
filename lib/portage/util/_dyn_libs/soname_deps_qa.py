# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io

from portage import (
	_encodings,
	_unicode_encode,
	os,
)
from portage.dep.soname.parse import parse_soname_deps
from portage.util._dyn_libs.NeededEntry import NeededEntry


def _get_all_provides(vardb):
	"""
	Get all of the sonames provided by all of the installed packages.
	This does not bother to acquire a lock, since its pretty safe to
	assume that any packages merged or unmerged while this function
	is running must be irrelevant.

	@param vardb: an installed package database
	@type vardb: vardbapi
	@rtype: frozenset
	@return: a frozenset od SonameAtom instances provided by all
		installed packages
	"""

	all_provides = []

	for cpv in vardb.cpv_all():
		try:
			provides, = vardb.aux_get(cpv, ['PROVIDES'])
		except KeyError:
			# Since we don't hold a lock, assume this is due to a
			# concurrent unmerge, and PROVIDES from the unmerged package
			# are most likely negligible due to topologically sorted
			# merge order. Also, note that it's possible for aux_get
			# to succeed and return empty PROVIDES metadata if the file
			# disappears (due to unmerge) before it can be read.
			pass
		else:
			if provides:
				all_provides.extend(parse_soname_deps(provides))

	return frozenset(all_provides)


def _get_unresolved_soname_deps(metadata_dir, all_provides):
	"""
	Get files with unresolved soname dependencies.

	@param metadata_dir: directory containing package metadata files
		named REQUIRES and NEEDED.ELF.2
	@type metadata_dir: str
	@param all_provides: a frozenset on SonameAtom instances provided by
		all installed packages
	@type all_provides: frozenset
	@rtype: list
	@return: list of tuple(filename, tuple(unresolved sonames))
	"""
	try:
		with io.open(_unicode_encode(os.path.join(metadata_dir, 'REQUIRES'),
			encoding=_encodings['fs'], errors='strict'),
			mode='rt', encoding=_encodings['repo.content'], errors='strict') as f:
			requires = frozenset(parse_soname_deps(f.read()))
	except EnvironmentError:
		return []

	unresolved_by_category = {}
	for atom in requires:
		if atom not in all_provides:
			unresolved_by_category.setdefault(atom.multilib_category, set()).add(atom.soname)

	needed_filename = os.path.join(metadata_dir, "NEEDED.ELF.2")
	with io.open(_unicode_encode(needed_filename, encoding=_encodings['fs'], errors='strict'),
		mode='rt', encoding=_encodings['repo.content'], errors='strict') as f:
		needed = f.readlines()

	unresolved_by_file = []
	for l in needed:
		l = l.rstrip("\n")
		if not l:
			continue
		entry = NeededEntry.parse(needed_filename, l)
		missing = unresolved_by_category.get(entry.multilib_category)
		if not missing:
			continue
		# NOTE: This can contain some false positives in the case of
		# missing DT_RPATH settings, since it's possible that a subset
		# package files have the desired DT_RPATH settings. However,
		# since reported sonames are unresolved for at least some file(s),
		# false positives or this sort should not be not too annoying.
		missing = [soname for soname in entry.needed if soname in missing]
		if missing:
			unresolved_by_file.append((entry.filename, tuple(missing)))

	return unresolved_by_file
