# test_best_match_to_list.py -- Portage Unit Testing Functionality
# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import Atom, best_match_to_list

class Test_best_match_to_list(TestCase):

	def best_match_to_list_wrapper(self, mypkg, mylist):
		"""
		This function uses best_match_to_list to create sorted
		list of matching atoms.
		"""
		ret = []
		while mylist:
			m = best_match_to_list(mypkg, mylist)
			if m is not None:
				ret.append(m)
				mylist.remove(m)
			else:
				break

		return ret

	def testBest_match_to_list(self):
		tests = [
					("dev-libs/A-4", [Atom(">=dev-libs/A-3"), Atom(">=dev-libs/A-2")], \
						[Atom(">=dev-libs/A-3"), Atom(">=dev-libs/A-2")]),
					("dev-libs/A-4", [Atom("<=dev-libs/A-5"), Atom("<=dev-libs/A-6")], \
						[Atom("<=dev-libs/A-5"), Atom("<=dev-libs/A-6")]),
					("dev-libs/A-1", [Atom("dev-libs/A"), Atom("=dev-libs/A-1")], \
						[Atom("=dev-libs/A-1"), Atom("dev-libs/A")]),
					("dev-libs/A-1", [Atom("dev-libs/B"), Atom("=dev-libs/A-1:0")], \
						[Atom("=dev-libs/A-1:0")]),
					("dev-libs/A-1", [Atom("dev-libs/*", allow_wildcard=True), Atom("=dev-libs/A-1:0")], \
						[Atom("=dev-libs/A-1:0"), Atom("dev-libs/*", allow_wildcard=True)]),
					("dev-libs/A-1:0", [Atom("dev-*/*", allow_wildcard=True), Atom("dev-*/*:0", allow_wildcard=True),\
						Atom("dev-libs/A"), Atom("<=dev-libs/A-2"), Atom("dev-libs/A:0"), \
						Atom("=dev-libs/A-1*"), Atom("~dev-libs/A-1"), Atom("=dev-libs/A-1")], \
						[Atom("=dev-libs/A-1"), Atom("~dev-libs/A-1"), Atom("=dev-libs/A-1*"), \
						Atom("dev-libs/A:0"), Atom("<=dev-libs/A-2"), Atom("dev-libs/A"), \
						Atom("dev-*/*:0", allow_wildcard=True), Atom("dev-*/*", allow_wildcard=True)])
				]

		for pkg, atom_list, result in tests:
			self.assertEqual( self.best_match_to_list_wrapper( pkg, atom_list ), result )
