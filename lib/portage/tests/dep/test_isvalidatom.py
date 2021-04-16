# Copyright 2006-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.dep import isvalidatom

class IsValidAtomTestCase:
	def __init__(self, atom, expected, allow_wildcard=False,
		allow_repo=False, allow_build_id=False, eapi=None):
		self.atom = atom
		self.expected = expected
		self.allow_wildcard = allow_wildcard
		self.allow_repo = allow_repo
		self.allow_build_id = allow_build_id
		self.eapi = eapi

class IsValidAtom(TestCase):

	def testIsValidAtom(self):

		test_cases = (
			IsValidAtomTestCase("sys-apps/portage", True),
			IsValidAtomTestCase("=sys-apps/portage-2.1", True),
			IsValidAtomTestCase("=sys-apps/portage-2.1*", True),
			IsValidAtomTestCase(">=sys-apps/portage-2.1", True),
			IsValidAtomTestCase("<=sys-apps/portage-2.1", True),
			IsValidAtomTestCase(">sys-apps/portage-2.1", True),
			IsValidAtomTestCase("<sys-apps/portage-2.1", True),
			IsValidAtomTestCase("~sys-apps/portage-2.1", True),
			IsValidAtomTestCase("sys-apps/portage:foo", True),
			IsValidAtomTestCase("sys-apps/portage-2.1:foo", False),
			IsValidAtomTestCase("sys-apps/portage-2.1:", False),
			IsValidAtomTestCase("sys-apps/portage-2.1:", False),
			IsValidAtomTestCase("sys-apps/portage-2.1:[foo]", False),
			IsValidAtomTestCase("sys-apps/portage", True),
			IsValidAtomTestCase("sys-apps/portage", True),
			IsValidAtomTestCase("sys-apps/portage", True),
			IsValidAtomTestCase("sys-apps/portage", True),
			IsValidAtomTestCase("sys-apps/portage", True),
			IsValidAtomTestCase("sys-apps/portage", True),
			IsValidAtomTestCase("sys-apps/portage", True),

			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[bar?,!baz?,!doc=,build=]", True),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[doc?]", True),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[!doc?]", True),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[doc=]", True),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[!doc=]", True),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[!doc]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[!-doc]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[!-doc=]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[!-doc?]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[-doc?]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[-doc=]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[-doc!=]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[-doc=]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[bar][-baz][doc?][!build?]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[bar,-baz,doc?,!build?]", True),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[bar,-baz,doc?,!build?,]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[,bar,-baz,doc?,!build?]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[bar,-baz][doc?,!build?]", False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo[bar][doc,build]", False),
			IsValidAtomTestCase(">~cate-gory/foo-1.0", False),
			IsValidAtomTestCase(">~category/foo-1.0", False),
			IsValidAtomTestCase("<~category/foo-1.0", False),
			IsValidAtomTestCase("###cat/foo-1.0", False),
			IsValidAtomTestCase("~sys-apps/portage", False),
			IsValidAtomTestCase("portage", False),
			IsValidAtomTestCase("=portage", False),
			IsValidAtomTestCase(">=portage-2.1", False),
			IsValidAtomTestCase("~portage-2.1", False),
			IsValidAtomTestCase("=portage-2.1*", False),
			IsValidAtomTestCase("null/portage", True),
			IsValidAtomTestCase("null/portage*:0", False),
			IsValidAtomTestCase(">=null/portage-2.1", True),
			IsValidAtomTestCase(">=null/portage", False),
			IsValidAtomTestCase(">null/portage", False),
			IsValidAtomTestCase("=null/portage*", False),
			IsValidAtomTestCase("=null/portage", False),
			IsValidAtomTestCase("~null/portage", False),
			IsValidAtomTestCase("<=null/portage", False),
			IsValidAtomTestCase("<null/portage", False),
			IsValidAtomTestCase("~null/portage-2.1", True),
			IsValidAtomTestCase("=null/portage-2.1*", True),
			IsValidAtomTestCase("null/portage-2.1*", False),
			IsValidAtomTestCase("app-doc/php-docs-20071125", False),
			IsValidAtomTestCase("app-doc/php-docs-20071125-r2", False),
			IsValidAtomTestCase("=foo/bar-1-r1-1-r1", False),
			IsValidAtomTestCase("foo/-z-1", False),

			# These are invalid because pkg name must not end in hyphen
			# followed by numbers
			IsValidAtomTestCase("=foo/bar-1-r1-1-r1", False),
			IsValidAtomTestCase("=foo/bar-123-1", False),
			IsValidAtomTestCase("=foo/bar-123-1*", False),
			IsValidAtomTestCase("foo/bar-123", False),
			IsValidAtomTestCase("=foo/bar-123-1-r1", False),
			IsValidAtomTestCase("=foo/bar-123-1-r1*", False),
			IsValidAtomTestCase("foo/bar-123-r1", False),
			IsValidAtomTestCase("foo/bar-1", False),

			IsValidAtomTestCase("=foo/bar--baz-1-r1", True),
			IsValidAtomTestCase("=foo/bar-baz--1-r1", True),
			IsValidAtomTestCase("=foo/bar-baz---1-r1", True),
			IsValidAtomTestCase("=foo/bar-baz---1", True),
			IsValidAtomTestCase("=foo/bar-baz-1--r1", False),
			IsValidAtomTestCase("games-strategy/ufo2000", True),
			IsValidAtomTestCase("~games-strategy/ufo2000-0.1", True),
			IsValidAtomTestCase("=media-libs/x264-20060810", True),
			IsValidAtomTestCase("foo/b", True),
			IsValidAtomTestCase("app-text/7plus", True),
			IsValidAtomTestCase("foo/666", True),
			IsValidAtomTestCase("=dev-libs/poppler-qt3-0.11*", True),

			 #Testing atoms with repositories
			IsValidAtomTestCase("sys-apps/portage::repo_123-name", True, allow_repo=True),
			IsValidAtomTestCase("=sys-apps/portage-2.1::repo", True, allow_repo=True),
			IsValidAtomTestCase("=sys-apps/portage-2.1*::repo", True, allow_repo=True),
			IsValidAtomTestCase("sys-apps/portage:foo::repo", True, allow_repo=True),
			IsValidAtomTestCase("sys-apps/portage-2.1:foo::repo", False, allow_repo=True),
			IsValidAtomTestCase("sys-apps/portage-2.1:::repo", False, allow_repo=True),
			IsValidAtomTestCase("sys-apps/portage-2.1:::repo[foo]", False, allow_repo=True),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo::repo[bar?,!baz?,!doc=,build=]", True, allow_repo=True),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo::repo[doc?]", True, allow_repo=True),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo::repo[!doc]", False, allow_repo=True),
			IsValidAtomTestCase("###cat/foo-1.0::repo", False, allow_repo=True),
			IsValidAtomTestCase("~sys-apps/portage::repo", False, allow_repo=True),
			IsValidAtomTestCase("portage::repo", False, allow_repo=True),
			IsValidAtomTestCase("=portage::repo", False, allow_repo=True),
			IsValidAtomTestCase("null/portage::repo", True, allow_repo=True),
			IsValidAtomTestCase("app-doc/php-docs-20071125::repo", False, allow_repo=True),
			IsValidAtomTestCase("=foo/bar-1-r1-1-r1::repo", False, allow_repo=True),

			IsValidAtomTestCase("sys-apps/portage::repo_123-name", False, allow_repo=False),
			IsValidAtomTestCase("=sys-apps/portage-2.1::repo", False, allow_repo=False),
			IsValidAtomTestCase("=sys-apps/portage-2.1*::repo", False, allow_repo=False),
			IsValidAtomTestCase("sys-apps/portage:foo::repo", False, allow_repo=False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo::repo[bar?,!baz?,!doc=,build=]", False, allow_repo=False),
			IsValidAtomTestCase("=sys-apps/portage-2.2*:foo::repo[doc?]", False, allow_repo=False),
			IsValidAtomTestCase("null/portage::repo", False, allow_repo=False),

			# Testing repo atoms with eapi

			# If allow_repo is None, it should be overwritten by eapi
			IsValidAtomTestCase("sys-apps/portage::repo", True, allow_repo=None),
			IsValidAtomTestCase("sys-apps/portage::repo", False, allow_repo=None, eapi="5"),
			IsValidAtomTestCase("sys-apps/portage::repo", True,  allow_repo=None, eapi="5-progress"),
			IsValidAtomTestCase("sys-apps/portage::repo", False, allow_repo=None, eapi="7"),

			# If allow_repo is not None, it should not be overwritten by eapi
			IsValidAtomTestCase("sys-apps/portage::repo", False, allow_repo=False),
			IsValidAtomTestCase("sys-apps/portage::repo", False, allow_repo=False, eapi="5"),
			IsValidAtomTestCase("sys-apps/portage::repo", False,  allow_repo=False, eapi="5-progress"),
			IsValidAtomTestCase("sys-apps/portage::repo", False, allow_repo=False, eapi="7"),
			IsValidAtomTestCase("sys-apps/portage::repo", True, allow_repo=True),
			IsValidAtomTestCase("sys-apps/portage::repo", True, allow_repo=True, eapi="5"),
			IsValidAtomTestCase("sys-apps/portage::repo", True,  allow_repo=True, eapi="5-progress"),
			IsValidAtomTestCase("sys-apps/portage::repo", True, allow_repo=True, eapi="7"),

			IsValidAtomTestCase("virtual/ffmpeg:0/53", True),
			IsValidAtomTestCase("virtual/ffmpeg:0/53=", True),
			IsValidAtomTestCase("virtual/ffmpeg:0/53*", False),
			IsValidAtomTestCase("virtual/ffmpeg:=", True),
			IsValidAtomTestCase("virtual/ffmpeg:0=", True),
			IsValidAtomTestCase("virtual/ffmpeg:*", True),
			IsValidAtomTestCase("virtual/ffmpeg:0*", False),
			IsValidAtomTestCase("virtual/ffmpeg:0", True),

			# Wildcard atoms
			IsValidAtomTestCase("*/portage-2.1", False, allow_wildcard=True),
		)

		for test_case in test_cases:
			if test_case.expected:
				atom_type = "valid"
			else:
				atom_type = "invalid"
			self.assertEqual(bool(isvalidatom(test_case.atom, allow_wildcard=test_case.allow_wildcard,
				allow_repo=test_case.allow_repo,
				allow_build_id=test_case.allow_build_id,
				eapi=test_case.eapi)),
				test_case.expected,
				msg="isvalidatom(%s) != %s" % (test_case.atom, test_case.expected))
