# test_best_match_to_list.py -- Portage Unit Testing Functionality
# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import permutations

from portage.tests import TestCase
from portage.dep import Atom, best_match_to_list

class Test_best_match_to_list(TestCase):

	def best_match_to_list_wrapper(self, mypkg, mylist):
		"""
		This function uses best_match_to_list to create sorted
		list of matching atoms.
		"""
		ret = []
		mylist = list(mylist)
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
			("dev-libs/A-4", [Atom(">=dev-libs/A-3"), Atom(">=dev-libs/A-2")],
				[Atom(">=dev-libs/A-3"), Atom(">=dev-libs/A-2")], True),
			("dev-libs/A-4", [Atom("<=dev-libs/A-5"), Atom("<=dev-libs/A-6")],
				[Atom("<=dev-libs/A-5"), Atom("<=dev-libs/A-6")], True),
			("dev-libs/A-1", [Atom("dev-libs/A"), Atom("=dev-libs/A-1")],
				[Atom("=dev-libs/A-1"), Atom("dev-libs/A")], True),
			("dev-libs/A-1", [Atom("dev-libs/B"), Atom("=dev-libs/A-1:0")],
				[Atom("=dev-libs/A-1:0")], True),
			("dev-libs/A-1", [Atom("dev-libs/*", allow_wildcard=True), Atom("=dev-libs/A-1:0")],
				[Atom("=dev-libs/A-1:0"), Atom("dev-libs/*", allow_wildcard=True)], True),
			("dev-libs/A-4.9999-r1", [Atom("dev-libs/*", allow_wildcard=True), Atom("=*/*-*9999*", allow_wildcard=True)],
				[Atom("=*/*-*9999*", allow_wildcard=True), Atom("dev-libs/*", allow_wildcard=True)], True),
			("dev-libs/A-4_beta-r1", [Atom("dev-libs/*", allow_wildcard=True), Atom("=*/*-*_beta*", allow_wildcard=True)],
				[Atom("=*/*-*_beta*", allow_wildcard=True), Atom("dev-libs/*", allow_wildcard=True)], True),
			("dev-libs/A-4_beta1-r1", [Atom("dev-libs/*", allow_wildcard=True), Atom("=*/*-*_beta*", allow_wildcard=True)],
				[Atom("=*/*-*_beta*", allow_wildcard=True), Atom("dev-libs/*", allow_wildcard=True)], True),
			("dev-libs/A-1:0", [Atom("dev-*/*", allow_wildcard=True), Atom("dev-*/*:0", allow_wildcard=True),
				Atom("dev-libs/A"), Atom("<=dev-libs/A-2"), Atom("dev-libs/A:0"),
				Atom("=dev-libs/A-1*"), Atom("~dev-libs/A-1"), Atom("=dev-libs/A-1")],
				[Atom("=dev-libs/A-1"), Atom("~dev-libs/A-1"), Atom("=dev-libs/A-1*"),
				Atom("dev-libs/A:0"), Atom("<=dev-libs/A-2"), Atom("dev-libs/A"),
				Atom("dev-*/*:0", allow_wildcard=True), Atom("dev-*/*", allow_wildcard=True)], False)
		]

		for pkg, atom_list, result, all_permutations in tests:
			if all_permutations:
				atom_lists = permutations(atom_list)
			else:
				atom_lists = [atom_list]
			for atom_list in atom_lists:
				self.assertEqual(
					self.best_match_to_list_wrapper(pkg, atom_list),
					result)
