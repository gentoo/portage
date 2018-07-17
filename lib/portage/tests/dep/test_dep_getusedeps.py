# test_dep_getusedeps.py -- Portage Unit Testing Functionality
# Copyright 2007-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import dep_getusedeps

from portage.tests import test_cps, test_slots, test_versions, test_usedeps

class DepGetUseDeps(TestCase):
	""" A simple testcase for dep_getusedeps
	"""

	def testDepGetUseDeps(self):

		for mycpv in test_cps:
			for version in test_versions:
				for slot in test_slots:
					for use in test_usedeps:
						cpv = mycpv[:]
						if version:
							cpv += version
						if slot:
							cpv += ":" + slot
						if isinstance(use, tuple):
							cpv += "[%s]" % (",".join(use),)
							self.assertEqual(dep_getusedeps(
								cpv), use)
						else:
							if len(use):
								self.assertEqual(dep_getusedeps(
									cpv + "[" + use + "]"), (use,))
							else:
								self.assertEqual(dep_getusedeps(
									cpv + "[" + use + "]"), ())
