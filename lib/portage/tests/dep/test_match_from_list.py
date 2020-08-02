# Copyright 2006-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import Atom, match_from_list, _repo_separator
from portage.versions import catpkgsplit, _pkg_str


class Package:
	"""
	Provides a minimal subset of attributes of _emerge.Package.Package
	"""
	def __init__(self, atom):
		atom = Atom(atom, allow_repo=True)
		self.cp = atom.cp
		slot = atom.slot
		if atom.sub_slot:
			slot = "%s/%s" % (slot, atom.sub_slot)
		if not slot:
			slot = '0'
		self.cpv = _pkg_str(atom.cpv, slot=slot, repo=atom.repo)
		self.cpv_split = catpkgsplit(self.cpv)
		self.slot = self.cpv.slot
		self.sub_slot = self.cpv.sub_slot
		self.repo = atom.repo
		if atom.use:
			self.use = self._use_class(atom.use.enabled)
			self.iuse = self._iuse_class(atom.use.required)
		else:
			self.use = self._use_class([])
			self.iuse = self._iuse_class([])

	class _use_class:
		def __init__(self, use):
			self.enabled = frozenset(use)

	class _iuse_class:
		def __init__(self, iuse):
			self.all = frozenset(iuse)

		def is_valid_flag(self, flags):
			if isinstance(flags, str):
				flags = [flags]
			for flag in flags:
				if not flag in self.all:
					return False
			return True

class Test_match_from_list(TestCase):

	def testMatch_from_list(self):
		tests = (
			("=sys-apps/portage-45*", [], []),
			("=sys-apps/portage-45*", ["sys-apps/portage-045"], ["sys-apps/portage-045"]),
			("!=sys-apps/portage-45*", ["sys-apps/portage-045"], ["sys-apps/portage-045"]),
			("!!=sys-apps/portage-45*", ["sys-apps/portage-045"], ["sys-apps/portage-045"]),
			("=sys-apps/portage-045", ["sys-apps/portage-045"], ["sys-apps/portage-045"]),
			("=sys-apps/portage-045", ["sys-apps/portage-046"], []),
			("~sys-apps/portage-045", ["sys-apps/portage-045-r1"], ["sys-apps/portage-045-r1"]),
			("~sys-apps/portage-045", ["sys-apps/portage-046-r1"], []),
			("<=sys-apps/portage-045", ["sys-apps/portage-045"], ["sys-apps/portage-045"]),
			("<=sys-apps/portage-045", ["sys-apps/portage-046"], []),
			("<sys-apps/portage-046", ["sys-apps/portage-045"], ["sys-apps/portage-045"]),
			("<sys-apps/portage-046", ["sys-apps/portage-046"], []),
			(">=sys-apps/portage-045", ["sys-apps/portage-045"], ["sys-apps/portage-045"]),
			(">=sys-apps/portage-047", ["sys-apps/portage-046-r1"], []),
			(">sys-apps/portage-044", ["sys-apps/portage-045"], ["sys-apps/portage-045"]),
			(">sys-apps/portage-047", ["sys-apps/portage-046-r1"], []),
			("sys-apps/portage:0", [Package("=sys-apps/portage-045:0")], ["sys-apps/portage-045"]),
			("sys-apps/portage:0", [Package("=sys-apps/portage-045:1")], []),
			("=cat/pkg-1-r1*", ["cat/pkg-1_alpha1"], []),
			# =* glob matches only on boundaries between version parts,
			# so 1* does not match 10 (bug 560466).
			("=cat/pkg-1.1*", ["cat/pkg-1.1-r1", "cat/pkg-1.10-r1"], ["cat/pkg-1.1-r1"]),
			("=cat/pkg-1-r1*", ["cat/pkg-1-r11"], []),
			("=cat/pkg-1_pre*", ["cat/pkg-1_pre1"], ["cat/pkg-1_pre1"]),
			("=cat/pkg-1-r1*", ["cat/pkg-1-r1"], ["cat/pkg-1-r1"]),
			("=cat/pkg-1-r11*", ["cat/pkg-1-r11"], ["cat/pkg-1-r11"]),
			("=cat/pkg-1-r11*", ["cat/pkg-01-r11"], ["cat/pkg-01-r11"]),
			("=cat/pkg-01-r11*", ["cat/pkg-1-r11"], ["cat/pkg-1-r11"]),
			("=cat/pkg-01-r11*", ["cat/pkg-001-r11"], ["cat/pkg-001-r11"]),
			("=sys-fs/udev-1*", ["sys-fs/udev-123", "sys-fs/udev-123-r1"], []),
			("=sys-fs/udev-123*", ["sys-fs/udev-123"], ["sys-fs/udev-123"]),
			("=sys-fs/udev-123*", ["sys-fs/udev-123-r1"], ["sys-fs/udev-123-r1"]),
			("=sys-fs/udev-4*", ["sys-fs/udev-456", "sys-fs/udev-456-r1"], []),
			("=sys-fs/udev-456*", ["sys-fs/udev-456"], ["sys-fs/udev-456"]),
			("*/*", ["sys-fs/udev-456"], ["sys-fs/udev-456"]),
			("*/*:0", ["sys-fs/udev-456:0"], ["sys-fs/udev-456:0"]),
			("*/*:1", ["sys-fs/udev-456:0"], []),
			("sys-fs/*", ["sys-fs/udev-456"], ["sys-fs/udev-456"]),
			("*/udev", ["sys-fs/udev-456"], ["sys-fs/udev-456"]),
			("=sys-apps/portage-2*", ["sys-apps/portage-2.1"], ["sys-apps/portage-2.1"]),
			("=sys-apps/portage-2.1*", ["sys-apps/portage-2.1.2"], ["sys-apps/portage-2.1.2"]),
			("dev-libs/*", ["sys-apps/portage-2.1.2"], []),
			("*/tar", ["sys-apps/portage-2.1.2"], []),
			("*/*", ["dev-libs/A-1", "dev-libs/B-1"], ["dev-libs/A-1", "dev-libs/B-1"]),
			("dev-libs/*", ["dev-libs/A-1", "sci-libs/B-1"], ["dev-libs/A-1"]),

			("dev-libs/A[foo]", [Package("=dev-libs/A-1[foo]"), Package("=dev-libs/A-2[-foo]")], ["dev-libs/A-1"]),
			("dev-libs/A[-foo]", [Package("=dev-libs/A-1[foo]"), Package("=dev-libs/A-2[-foo]")], ["dev-libs/A-2"]),
			("dev-libs/A[-foo]", [Package("=dev-libs/A-1[foo]"), Package("=dev-libs/A-2")], []),
			("dev-libs/A[foo,bar]", [Package("=dev-libs/A-1[foo]"), Package("=dev-libs/A-2[-foo]")], []),
			("dev-libs/A[foo,bar]", [Package("=dev-libs/A-1[foo]"), Package("=dev-libs/A-2[-foo,bar]")], []),
			("dev-libs/A[foo,bar]", [Package("=dev-libs/A-1[foo]"), Package("=dev-libs/A-2[foo,bar]")], ["dev-libs/A-2"]),
			("dev-libs/A[foo,bar(+)]", [Package("=dev-libs/A-1[-foo]"), Package("=dev-libs/A-2[foo]")], ["dev-libs/A-2"]),
			("dev-libs/A[foo,bar(-)]", [Package("=dev-libs/A-1[-foo]"), Package("=dev-libs/A-2[foo]")], []),
			("dev-libs/A[foo,-bar(-)]", [Package("=dev-libs/A-1[-foo,bar]"), Package("=dev-libs/A-2[foo]")], ["dev-libs/A-2"]),

			("dev-libs/A::repo1", [Package("=dev-libs/A-1::repo1"), Package("=dev-libs/A-1::repo2")], ["dev-libs/A-1::repo1"]),
			("dev-libs/A::repo2", [Package("=dev-libs/A-1::repo1"), Package("=dev-libs/A-1::repo2")], ["dev-libs/A-1::repo2"]),
			("dev-libs/A::repo2[foo]", [Package("=dev-libs/A-1::repo1[foo]"), Package("=dev-libs/A-1::repo2[-foo]")], []),
			("dev-libs/A::repo2[foo]", [Package("=dev-libs/A-1::repo1[-foo]"), Package("=dev-libs/A-1::repo2[foo]")], ["dev-libs/A-1::repo2"]),
			("dev-libs/A:1::repo2[foo]", [Package("=dev-libs/A-1:1::repo1"), Package("=dev-libs/A-1:2::repo2")], []),
			("dev-libs/A:1::repo2[foo]", [Package("=dev-libs/A-1:2::repo1"), Package("=dev-libs/A-1:1::repo2[foo]")], ["dev-libs/A-1::repo2"]),

			("virtual/ffmpeg:0/53", [Package("=virtual/ffmpeg-0.10.3:0/53")], ["virtual/ffmpeg-0.10.3"]),
			("virtual/ffmpeg:0/53=", [Package("=virtual/ffmpeg-0.10.3:0/53")], ["virtual/ffmpeg-0.10.3"]),
			("virtual/ffmpeg:0/52", [Package("=virtual/ffmpeg-0.10.3:0/53")], []),
			("virtual/ffmpeg:=", [Package("=virtual/ffmpeg-0.10.3:0/53")], ["virtual/ffmpeg-0.10.3"]),
			("virtual/ffmpeg:0=", [Package("=virtual/ffmpeg-0.10.3:0/53")], ["virtual/ffmpeg-0.10.3"]),
			("virtual/ffmpeg:*", [Package("=virtual/ffmpeg-0.10.3:0/53")], ["virtual/ffmpeg-0.10.3"]),
			("virtual/ffmpeg:0", [Package("=virtual/ffmpeg-0.10.3:0/53")], ["virtual/ffmpeg-0.10.3"]),

			("sys-libs/db:4.8/4.8", [Package("=sys-libs/db-4.8.30:4.8")], ["sys-libs/db-4.8.30"]),
			("sys-libs/db:4.8/4.8=", [Package("=sys-libs/db-4.8.30:4.8")], ["sys-libs/db-4.8.30"]),
			("sys-libs/db:4.8=", [Package("=sys-libs/db-4.8.30:4.8")], ["sys-libs/db-4.8.30"]),
			("sys-libs/db:*", [Package("=sys-libs/db-4.8.30:4.8")], ["sys-libs/db-4.8.30"]),
			("sys-libs/db:4.8/0", [Package("=sys-libs/db-4.8.30:4.8")], []),
			("sys-libs/db:4.8/0=", [Package("=sys-libs/db-4.8.30:4.8")], []),
		)

		for atom, cpv_list, expected_result in tests:
			result = []
			for pkg in match_from_list(atom, cpv_list):
				if isinstance(pkg, Package):
					if pkg.repo:
						result.append(pkg.cpv + _repo_separator + pkg.repo)
					else:
						result.append(pkg.cpv)
				else:
					result.append(pkg)
			self.assertEqual(result, expected_result)
