# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'ordered_by_atom_specificity',
)

from portage.dep import best_match_to_list

def ordered_by_atom_specificity(cpdict, pkg):
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
