

import re

from repoman.modules.linechecks.base import LineCheck


class EbuildPatches(LineCheck):
	"""Ensure ebuilds use bash arrays for PATCHES to ensure white space safety"""
	repoman_check_name = 'ebuild.patches'
	re = re.compile(r'^\s*PATCHES=[^\(]')
	error = 'PATCHES_ERROR'

	def check_eapi(self, eapi):
		return eapi in ("0", "1", "2", "3", "4", "4-python",
			"4-slot-abi", "5", "5-hdepend", "5-progress")
