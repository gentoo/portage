# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import collections

from portage.dep import Atom
from portage.tests import TestCase
from _emerge.resolver.package_tracker import PackageTracker, PackageTrackerDbapiWrapper

class PackageTrackerTestCase(TestCase):

	FakePackage = collections.namedtuple("FakePackage",
		["root", "cp", "cpv", "slot", "slot_atom", "version", "repo"])

	FakeConflict = collections.namedtuple("FakeConflict",
		["description", "root", "pkgs"])

	def make_pkg(self, root, atom, repo="test_repo"):
		atom = Atom(atom)
		slot_atom = Atom("%s:%s" % (atom.cp, atom.slot))
		slot = atom.slot

		return self.FakePackage(root=root, cp=atom.cp, cpv=atom.cpv,
			slot=slot, slot_atom=slot_atom, version=atom.version, repo=repo)

	def make_conflict(self, description, root, pkgs):
		return self.FakeConflict(description=description, root=root, pkgs=pkgs)

	def test_add_remove_discard(self):
		p = PackageTracker()

		x1 = self.make_pkg("/", "=dev-libs/X-1:0")
		x2 = self.make_pkg("/", "=dev-libs/X-2:0")

		p.add_pkg(x1)
		self.assertTrue(x1 in p)
		self.assertTrue(p.contains(x1, installed=True))
		self.assertTrue(p.contains(x1, installed=False))
		p.remove_pkg(x1)
		self.assertTrue(x1 not in p)

		p.add_pkg(x1)
		self.assertTrue(x1 in p)
		p.add_pkg(x1)
		self.assertTrue(x1 in p)

		self.assertRaises(KeyError, p.remove_pkg, x2)

		p.add_pkg(x2)
		self.assertTrue(x2 in p)
		p.remove_pkg(x2)
		self.assertTrue(x2 not in p)
		p.discard_pkg(x2)
		self.assertTrue(x2 not in p)
		p.add_pkg(x2)
		self.assertTrue(x2 in p)

		all_pkgs = list(p.all_pkgs("/"))
		self.assertEqual(len(all_pkgs), 2)
		self.assertTrue(all_pkgs[0] is x1 and all_pkgs[1] is x2)

		self.assertEqual(len(list(p.all_pkgs("/"))), 2)
		self.assertEqual(len(list(p.all_pkgs("/xxx"))), 0)

	def test_match(self):
		p = PackageTracker()
		x1 = self.make_pkg("/", "=dev-libs/X-1:0")
		x2 = self.make_pkg("/", "=dev-libs/X-2:0")
		x3 = self.make_pkg("/", "=dev-libs/X-3:1")

		p.add_pkg(x2)
		p.add_pkg(x1)

		matches = list(p.match("/", Atom("=dev-libs/X-1")))
		self.assertTrue(x1 in matches)
		self.assertEqual(len(matches), 1)

		matches = list(p.match("/", Atom("dev-libs/X")))
		self.assertTrue(x1 is matches[0] and x2 is matches[1])
		self.assertEqual(len(matches), 2)

		matches = list(p.match("/xxx", Atom("dev-libs/X")))
		self.assertEqual(len(matches), 0)

		matches = list(p.match("/", Atom("dev-libs/Y")))
		self.assertEqual(len(matches), 0)

		p.add_pkg(x3)
		matches = list(p.match("/", Atom("dev-libs/X")))
		self.assertTrue(x1 is matches[0] and x2 is matches[1] and x3 is matches[2])
		self.assertEqual(len(matches), 3)

		p.remove_pkg(x3)
		matches = list(p.match("/", Atom("dev-libs/X")))
		self.assertTrue(x1 is matches[0] and x2 is matches[1])
		self.assertEqual(len(matches), 2)

	def test_dbapi_interface(self):
		p = PackageTracker()
		dbapi = PackageTrackerDbapiWrapper("/", p)
		installed = self.make_pkg("/", "=dev-libs/X-0:0")
		x1 = self.make_pkg("/", "=dev-libs/X-1:0")
		x2 = self.make_pkg("/", "=dev-libs/X-2:0")
		x3 = self.make_pkg("/", "=dev-libs/X-3:0")
		x4 = self.make_pkg("/", "=dev-libs/X-4:6")
		x5 = self.make_pkg("/xxx", "=dev-libs/X-5:6")

		def check_dbapi(pkgs):
			all_pkgs = set(dbapi)
			self.assertEqual(len(all_pkgs), len(pkgs))

			x_atom = "dev-libs/X"
			y_atom = "dev-libs/Y"
			matches = dbapi.cp_list(x_atom)
			for pkg in pkgs:
				if pkg.root == "/" and pkg.cp == x_atom:
					self.assertTrue(pkg in matches)
			self.assertTrue(not dbapi.cp_list(y_atom))
			matches = dbapi.match(Atom(x_atom))
			for pkg in pkgs:
				if pkg.root == "/" and pkg.cp == x_atom:
					self.assertTrue(pkg in matches)
			self.assertTrue(not dbapi.match(Atom(y_atom)))

		check_dbapi([])

		p.add_installed_pkg(installed)
		check_dbapi([installed])

		p.add_pkg(x1)
		check_dbapi([x1])

		p.remove_pkg(x1)
		check_dbapi([installed])

		dbapi.cpv_inject(x1)
		check_dbapi([x1])

		dbapi.cpv_inject(x2)
		check_dbapi([x1, x2])

		p.remove_pkg(x1)
		check_dbapi([x2])

		p.add_pkg(x5)
		check_dbapi([x2])


	def test_installed(self):
		p = PackageTracker()
		x1 = self.make_pkg("/", "=dev-libs/X-1:0")
		x1b = self.make_pkg("/", "=dev-libs/X-1.1:0")
		x2 = self.make_pkg("/", "=dev-libs/X-2:0")
		x3 = self.make_pkg("/", "=dev-libs/X-3:1")

		def check_installed(x, should_contain, num_pkgs):
			self.assertEqual(x in p, should_contain)
			self.assertEqual(p.contains(x), should_contain)
			self.assertEqual(p.contains(x1, installed=True), should_contain)
			self.assertEqual(p.contains(x1, installed=False), False)
			self.assertEqual(len(list(p.all_pkgs("/"))), num_pkgs)

		def check_matches(atom, expected):
			matches = list(p.match("/", Atom(atom)))
			self.assertEqual(len(matches), len(expected))
			for x, y in zip(matches, expected):
				self.assertTrue(x is y)

		p.add_installed_pkg(x1)
		check_installed(x1, True, 1)
		check_matches("dev-libs/X", [x1])

		p.add_installed_pkg(x1)
		check_installed(x1, True, 1)
		check_matches("dev-libs/X", [x1])

		p.add_pkg(x2)
		check_installed(x1, False, 1)
		check_matches("dev-libs/X", [x2])

		p.add_installed_pkg(x1)
		check_installed(x1, False, 1)
		check_matches("dev-libs/X", [x2])

		p.add_installed_pkg(x1b)
		check_installed(x1, False, 1)
		check_installed(x1b, False, 1)
		check_matches("dev-libs/X", [x2])

		p.remove_pkg(x2)
		check_installed(x1, True, 2)
		check_installed(x1b, True, 2)
		check_matches("dev-libs/X", [x1, x1b])

	def test_conflicts(self):
		p = PackageTracker()
		installed1 = self.make_pkg("/", "=dev-libs/X-0:0")
		installed2 = self.make_pkg("/", "=dev-libs/X-0.1:0")
		x1 = self.make_pkg("/", "=dev-libs/X-1:0")
		x2 = self.make_pkg("/", "=dev-libs/X-2:0")
		x3 = self.make_pkg("/", "=dev-libs/X-3:0")
		x4 = self.make_pkg("/", "=dev-libs/X-4:4")
		x4b = self.make_pkg("/", "=dev-libs/X-4:4b::x-repo")

		def check_conflicts(expected, slot_conflicts_only=False):
			if slot_conflicts_only:
				conflicts = list(p.slot_conflicts())
			else:
				conflicts = list(p.conflicts())
			self.assertEqual(len(conflicts), len(expected))
			for got, exp in zip(conflicts, expected):
				self.assertEqual(got.description, exp.description)
				self.assertEqual(got.root, exp.root)
				self.assertEqual(len(got.pkgs), len(exp.pkgs))
				self.assertEqual(len(got), len(exp.pkgs))
				for x, y in zip(got.pkgs, exp.pkgs):
					self.assertTrue(x is y)
				for x, y in zip(got, exp.pkgs):
					self.assertTrue(x is y)
				for x in exp.pkgs:
					self.assertTrue(x in got)

		check_conflicts([])
		check_conflicts([])

		p.add_installed_pkg(installed1)
		p.add_installed_pkg(installed2)
		check_conflicts([])

		p.add_pkg(x1)
		check_conflicts([])
		p.add_pkg(x2)
		check_conflicts([self.make_conflict("slot conflict", "/", [x1, x2])])
		p.add_pkg(x3)
		check_conflicts([self.make_conflict("slot conflict", "/", [x1, x2, x3])])
		p.remove_pkg(x3)
		check_conflicts([self.make_conflict("slot conflict", "/", [x1, x2])])
		p.remove_pkg(x2)
		check_conflicts([])
		p.add_pkg(x3)
		check_conflicts([self.make_conflict("slot conflict", "/", [x1, x3])])
		p.add_pkg(x2)
		check_conflicts([self.make_conflict("slot conflict", "/", [x1, x3, x2])])

		p.add_pkg(x4)
		check_conflicts([self.make_conflict("slot conflict", "/", [x1, x3, x2])])

		p.add_pkg(x4b)
		check_conflicts(
			[
			self.make_conflict("slot conflict", "/", [x1, x3, x2]),
			self.make_conflict("cpv conflict", "/", [x4, x4b]),
			]
			)

		check_conflicts(
			[
			self.make_conflict("slot conflict", "/", [x1, x3, x2]),
			],
			slot_conflicts_only=True
			)
