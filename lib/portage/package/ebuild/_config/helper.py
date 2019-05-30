# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'ordered_by_atom_specificity', 'prune_incremental',
)

from _emerge.Package import Package
from portage.dep import best_match_to_list, _repo_separator

def ordered_by_atom_specificity(cpdict, pkg, repo=None):
	"""
	Return a list of matched values from the given cpdict,
	in ascending order by atom specificity. The rationale
	for this order is that package.* config files are
	typically written in ChangeLog like fashion, so it's
	most friendly if the order that the atoms are written
	does not matter. Therefore, settings from more specific
	atoms override those of less specific atoms. Without
	this behavior, settings from relatively unspecific atoms
	would (somewhat confusingly) override the settings of
	more specific atoms, requiring people to make adjustments
	to the order that atoms are listed in the config file in
	order to achieve desired results (and thus corrupting
	the ChangeLog like ordering of the file).
	"""
	if not hasattr(pkg, 'repo') and repo and repo != Package.UNKNOWN_REPO:
		pkg = pkg + _repo_separator + repo

	results = []
	keys = list(cpdict)

	while keys:
		bestmatch = best_match_to_list(pkg, keys)
		if bestmatch:
			keys.remove(bestmatch)
			results.append(cpdict[bestmatch])
		else:
			break

	if results:
		# reverse, so the most specific atoms come last
		results.reverse()

	return results

def prune_incremental(split):
	"""
	Prune off any parts of an incremental variable that are
	made irrelevant by the latest occuring * or -*. This
	could be more aggressive but that might be confusing
	and the point is just to reduce noise a bit.
	"""
	for i, x in enumerate(reversed(split)):
		if x == '*':
			split = split[-i-1:]
			break
		elif x == '-*':
			if i == 0:
				# Preserve the last -*, since otherwise an empty value
				# would trigger fallback to a default value.
				split = ['-*']
			else:
				split = split[-i:]
			break
	return split
