
'''repoman/checks/ebuilds/misc.py
Miscelaneous ebuild check functions'''

import re

# import our initialized portage instance
from repoman._portage import portage


pv_toolong_re = re.compile(r'[0-9]{19,}')


def bad_split_check(xpkg, y_ebuild, pkgdir, qatracker):
	'''Checks for bad category/package splits.

	@param xpkg: the pacakge being checked
	@param y_ebuild: string of the ebuild name being tested
	@param pkgdir: string: path
	@param qatracker: QATracker instance
	'''
	myesplit = portage.pkgsplit(y_ebuild)

	is_bad_split = myesplit is None or myesplit[0] != xpkg.split("/")[-1]

	if is_bad_split:
		is_pv_toolong = pv_toolong_re.search(myesplit[1])
		is_pv_toolong2 = pv_toolong_re.search(myesplit[2])

		if is_pv_toolong or is_pv_toolong2:
			qatracker.add_error(
				"ebuild.invalidname", xpkg + "/" + y_ebuild + ".ebuild")
			return True
	elif myesplit[0] != pkgdir:
		print(pkgdir, myesplit[0])
		qatracker.add_error(
			"ebuild.namenomatch", xpkg + "/" + y_ebuild + ".ebuild")
		return True
	return False


def pkg_invalid(pkg, qatracker, ebuild):
	'''Checks for invalid packages

	@param pkg: _emerge.Package instance
	@param qatracker: QATracker instance
	@return boolean:
	'''
	if pkg.invalid:
		for k, msgs in pkg.invalid.items():
			for msg in msgs:
				qatracker.add_error(k, "%s: %s" % (ebuild.relative_path, msg))
		return True
	return False
