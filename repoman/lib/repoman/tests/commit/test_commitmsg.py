# Copyright 2011-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from repoman.actions import Actions
from repoman.tests import TestCase


class CommitMessageVerificationTest(TestCase):
	def assertGood(self, commitmsg):
		res, expl = Actions.verify_commit_message(commitmsg)
		self.assertTrue(res,
				'''Commit message verification failed for:
%s

Error:
%s''' % (commitmsg, expl))

	def assertBad(self, commitmsg, reason_re):
		res, expl = Actions.verify_commit_message(commitmsg)
		self.assertFalse(res,
				'''Commit message verification succeeded unexpectedly, for:
%s

Expected: /%s/''' % (commitmsg, reason_re))
		self.assertNotIn('\n', expl.strip(),
				'''Commit message verification returned multiple errors (one expected):
%s

Expected: /%s/
Errors:
%s''' % (commitmsg, reason_re, expl))
		(self.assertRegex if hasattr(self, 'assertRegex') else self.assertRegexpMatches)(expl, reason_re,
				'''Commit message verification did not return expected error, for:
%s

Expected: /%s/
Errors:
%s''' % (commitmsg, reason_re, expl))

	def test_summary_only(self):
		self.assertGood('dev-foo/bar: Actually good commit message')

	def test_summary_and_body(self):
		self.assertGood('''dev-foo/bar: Good commit message

Extended description goes here and is properly wrapped at 72 characters
which is very nice and blah blah.

Another paragraph for the sake of having one.''')

	def test_summary_and_footer(self):
		self.assertGood('''dev-foo/bar: Good commit message

Closes: https://bugs.gentoo.org/NNNNNN''')

	def test_summary_body_and_footer(self):
		self.assertGood('''dev-foo/bar: Good commit message

Extended description goes here and is properly wrapped at 72 characters
which is very nice and blah blah.

Another paragraph for the sake of having one.

Closes: https://bugs.gentoo.org/NNNNNN''')

	def test_summary_without_unit_name(self):
		self.assertBad('Version bump', r'summary.*logical unit name')

	def test_multiline_summary(self):
		self.assertBad('''dev-foo/bar: Commit message with very long summary
that got wrapped because of length''', r'single.*line.*summary')

	def test_overlong_summary(self):
		self.assertBad('dev-foo/bar: Commit message with very long summary \
in a single line that should trigger an explicit error',
				r'summary.*too long')

	def test_summary_with_very_long_package_name(self):
		self.assertGood('dev-foo/foo-bar-bar-baz-bar-bar-foo-bar-bar-\
baz-foo-baz-baz-foo: We do not fail because pkgname was long')

	def test_multiple_footers(self):
		self.assertBad('''dev-foo/bar: Good summary

Bug: https://bugs.gentoo.org/NNNNNN

Closes: https://github.com/gentoo/gentoo/pull/NNNN''', r'multiple footer')

	def test_gentoo_bug(self):
		self.assertBad('''dev-foo/bar: Good summary

Gentoo-Bug: NNNNNN''', r'Gentoo-Bug')

	def test_bug_with_number(self):
		self.assertBad('''dev-foo/bar: Good summary

Bug: NNNNNN''', r'Bug.*full URL')

	def test_closes_with_number(self):
		self.assertBad('''dev-foo/bar: Good summary

Closes: NNNNNN''', r'Closes.*full URL')

	def test_body_too_long(self):
		self.assertBad('''dev-foo/bar: Good summary

But the body is not wrapped properly and has very long lines that are \
very hard to read and blah blah blah
blah blah.''', r'body.*wrapped')
