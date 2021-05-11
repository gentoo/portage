# Copyright 2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from _emerge.unmerge import _unmerge_display

from portage.tests import TestCase
from portage.tests.resolver.ResolverPlayground import ResolverPlayground

class _TestData:
	def __init__(self, unmerge_files, expected_pkgmap):
		self.unmerge_files = unmerge_files

		# The pkgmap created by unmerge_display is a list where each entry is of the form
		# {"selected": list(...), "omitted": set(...), "protected": set(...) }.
		# To simplify the notation of the test data, we receive a list with entries of the form
		# (s1,o1)
		# The entries are then translated to the expected form:
		# {"selected": s1, "omitted": o1, "protected": set()}
		# The "protected" field is not relevant for testing ordering.
		# The ordering of the "omitted" field is not relevant.
		expand = lambda x: {"selected": x[0], "omitted": set(x[1]), "protected": set()}
		self.expected_pkgmap = list(map(expand, expected_pkgmap))

class UnmergeOrderTestCase(TestCase):

	def testUnmergeOrder(self):
		ebuilds = {
			"c/x-1": {},

			"c/y-2": {},
			"c/y-3": {},

			"c/z-4": {},
			"c/z-5": {},
			"c/z-6": {},

			"c/zz-4": {},
			"c/zz-5": {},
			"c/zz-6": {},
		}
		installed = {
			"c/x-1": {},

			"c/y-2": {},

			"c/z-4": {},
			"c/z-5": {},
			"c/z-6": {},

			"c/zz-4": {},
			"c/zz-5": {},
			"c/zz-6": {},
		}
		test_cases = (

			# cp = category/package
			# cpv = category/package-version

			# Single cpv atom, representing the only available instance of the cp.
			# The pkgmap should contain exactly that cpv and no omitted packages.
			_TestData(["c/x-1"], [ (["c/x-1"],[]) ]),

			# Single cp atom. The pkgmap should contain the only available cpv to
			# which the cp expands, no omitted packages.
			_TestData(["c/x"], [ (["c/x-1"],[]) ]),

			# Duplicate cpv atom, representing the only available instance of the cp.
			# The pkgmap should contain the cpv with no omitted packages, and an empty
			# entry representing the duplicate.
			_TestData(["c/x-1", "c/x-1"], [ (["c/x-1"],[]), ([],[]) ]),

			# Duplicate cp atom, representing the only available instance. The pkgmap
			# should contain the only available cpv to which the cp expands, with no
			# omitted packages, and a second empty entry representing the duplicate.
			_TestData(["c/x", "c/x"], [ (["c/x-1"],[]), ([],[]) ]),

			# Single cpv atom, representing one of the two available instances. The
			# pkgmap should contain exactly that cpv. Since the other instance is not
			# installed, there should be no omitted packages.
			_TestData(["c/y-2"], [ (["c/y-2"],[]) ]),

			# Single cp atom. The pkgmap should contain exactly the only installed
			# instance and no omitted packages.
			_TestData(["c/y"], [ (["c/y-2"],[]) ]),

			# Single cpv atom, representing one of the three available instances.
			# The pkgmap should contain exactly the cpv. Since all three instances
			# are installed, the other two instances should be in the omitted packages.
			_TestData(["c/z-4"], [ (["c/z-4"],["c/z-5","c/z-6"]) ]),

			# Single cp atom. The pkgmap should contain all three installed instances.
			# Since there are no other installed instances, there should be no omitted
			# packages.
			_TestData(["c/z"], [ (["c/z-4","c/z-5","c/z-6"],[]) ]),

			# Two cpv atoms belonging to the same cp. The pkgmap should contain an
			# entry for each cpv, in the same order. The third installed cpv belonging
			# to the cp should be listed in the omitted section of each entry.
			_TestData(["c/z-4","c/z-5"], [ (["c/z-4"],["c/z-6"]), (["c/z-5"],["c/z-6"]) ]),
			_TestData(["c/z-5","c/z-4"], [ (["c/z-5"],["c/z-6"]), (["c/z-4"],["c/z-6"]) ]),

			# Three cpv atoms belonging to the same cp. The pkgmap should contain an
			# entry for each cpv, in the same order. Since there are no other instances
			# of the cp, the omitted section of each entry should be empty.
			_TestData(["c/z-4","c/z-5","c/z-6"], [ (["c/z-4"],[]), (["c/z-5"],[]), (["c/z-6"],[]) ]),
			_TestData(["c/z-6","c/z-5","c/z-4"], [ (["c/z-6"],[]), (["c/z-5"],[]), (["c/z-4"],[]) ]),

			# First a cp atom, then a cpv atom that is an instance of the cp. The
			# pkgmap should contain an entry containing all installed cpv's that the cp
			# expands to, in sorted order. It should then contain an empty entry
			# representing the input cpv that is already covered by the expansion of
			# the cp.
			_TestData(["c/z","c/z-4"], [ (["c/z-4","c/z-5","c/z-6"],[]), ([],[]) ]),
			_TestData(["c/z","c/z-6"], [ (["c/z-4","c/z-5","c/z-6"],[]), ([],[]) ]),

			# First a cpv atom, then the cp to which the cpv belongs. The pkgmap
			# should contain an entry for the first cpv, then an entry containing
			# the remaining cpv's to which the cp expands.
			_TestData(["c/z-4","c/z"], [ (["c/z-4"],[]), (["c/z-5","c/z-6"],[]) ]),
			_TestData(["c/z-6","c/z"], [ (["c/z-6"],[]), (["c/z-4","c/z-5"],[]) ]),

			# More mixed cp/cpv's. The cp should expand to all cpv's except those
			# covered by a preceding cpv. The cpv's after the cp should result in empty
			# entries, since they are already covered by the expansion of the cp.
			_TestData(["c/z","c/z-4","c/z-5"], [ (["c/z-4","c/z-5","c/z-6"],[]), ([],[]), ([],[]) ]),
			_TestData(["c/z","c/z-5","c/z-4"], [ (["c/z-4","c/z-5","c/z-6"],[]), ([],[]), ([],[]) ]),
			_TestData(["c/z-4","c/z","c/z-5"], [ (["c/z-4"],[]), (["c/z-5","c/z-6"],[]), ([],[]) ]),
			_TestData(["c/z-5","c/z","c/z-4"], [ (["c/z-5"],[]), (["c/z-4","c/z-6"],[]), ([],[]) ]),
			_TestData(["c/z-4","c/z-5","c/z"], [ (["c/z-4"],[]), (["c/z-5"],[]), (["c/z-6"],[]) ]),
			_TestData(["c/z-5","c/z-4","c/z"], [ (["c/z-5"],[]), (["c/z-4"],[]), (["c/z-6"],[]) ]),
			_TestData(["c/z","c/z-4","c/z-5","c/z-6"], [ (["c/z-4","c/z-5","c/z-6"],[]), ([],[]), ([],[]), ([],[]) ]),
			_TestData(["c/z","c/z-6","c/z-5","c/z-4"], [ (["c/z-4","c/z-5","c/z-6"],[]), ([],[]), ([],[]), ([],[]) ]),
			_TestData(["c/z-4","c/z","c/z-5","c/z-6"], [ (["c/z-4"],[]), (["c/z-5","c/z-6"],[]), ([],[]), ([],[]) ]),
			_TestData(["c/z-6","c/z","c/z-5","c/z-4"], [ (["c/z-6"],[]), (["c/z-4","c/z-5"],[]), ([],[]), ([],[]) ]),
			_TestData(["c/z-4","c/z-5","c/z","c/z-6"], [ (["c/z-4"],[]), (["c/z-5"],[]), (["c/z-6"],[]), ([],[]) ]),
			_TestData(["c/z-6","c/z-5","c/z","c/z-4"], [ (["c/z-6"],[]), (["c/z-5"],[]), (["c/z-4"],[]), ([],[]) ]),
			_TestData(["c/z-4","c/z-5","c/z-6","c/z"], [ (["c/z-4"],[]), (["c/z-5"],[]), (["c/z-6"],[]), ([],[]) ]),
			_TestData(["c/z-6","c/z-5","c/z-4","c/z"], [ (["c/z-6"],[]), (["c/z-5"],[]), (["c/z-4"],[]), ([],[]) ]),

			# Two cpv that do not belong to the same cp. The pkgmap should contain an
			# entry for each cpv, in the same order. If there are other installed
			# instances of the cp to which the cpv belongs, they should be listed
			# in the omitted section.
			_TestData(["c/x-1","c/y-2"], [ (["c/x-1"],[]), (["c/y-2"],[]) ]),
			_TestData(["c/y-2","c/x-1"], [ (["c/y-2"],[]), (["c/x-1"],[]) ]),
			_TestData(["c/x-1","c/z-4"], [ (["c/x-1"],[]), (["c/z-4"],["c/z-5","c/z-6"]) ]),
			_TestData(["c/z-4","c/x-1"], [ (["c/z-4"],["c/z-5","c/z-6"]), (["c/x-1"],[]) ]),

			# cpv's/cp where some cpv's are not instances of the cp. The pkgmap should
			# contain an entry for each in the same order, with the cp expanded
			# to all installed instances.
			_TestData(["c/x-1","c/z"], [ (["c/x-1"],[]), (["c/z-4","c/z-5","c/z-6"],[]) ]),
			_TestData(["c/z","c/x-1"], [ (["c/z-4","c/z-5","c/z-6"],[]), (["c/x-1"],[]) ]),
			_TestData(["c/x-1","c/z-4","c/z"], [ (["c/x-1"],[]), (["c/z-4"],[]), (["c/z-5","c/z-6"],[]) ]),
			_TestData(["c/z-4","c/z","c/x-1"], [ (["c/z-4"],[]), (["c/z-5","c/z-6"],[]), (["c/x-1"],[]) ]),
			_TestData(["c/x-1","c/z","c/z-4"], [ (["c/x-1"],[]), (["c/z-4","c/z-5","c/z-6"],[]), ([],[]) ]),
			_TestData(["c/z","c/z-4","c/x-1"], [ (["c/z-4","c/z-5","c/z-6"],[]), ([],[]), (["c/x-1"],[]) ]),

			# Two different cp's. The pkglist should contain an entry for each cp,
			# in the same order, containing all cpv's that the cp's expands to.
			_TestData(["c/z","c/zz"], [ (["c/z-4","c/z-5","c/z-6"],[]), (["c/zz-4","c/zz-5","c/zz-6"],[]) ]),
			_TestData(["c/zz","c/z"], [ (["c/zz-4","c/zz-5","c/zz-6"],[]), (["c/z-4","c/z-5","c/z-6"],[]) ]),
		)

		playground = ResolverPlayground(ebuilds=ebuilds, installed=installed)

		try:
			for test_case in test_cases:
				eroot = playground.settings['EROOT']
				root_config = playground.trees[eroot]["root_config"]

				res, pkgmap = _unmerge_display(root_config, [], "unmerge", test_case.unmerge_files, ordered=True)

				self.assertEqual(res, os.EX_OK)
				self.assertEqual(pkgmap, test_case.expected_pkgmap)
		finally:
			playground.cleanup()
