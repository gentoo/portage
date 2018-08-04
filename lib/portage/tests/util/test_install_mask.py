# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from portage.util.install_mask import InstallMask


class InstallMaskTestCase(TestCase):

	def testTrailingSlash(self):
		"""
		Test that elements with a trailing slash match a directory
		but not a regular file.
		"""
		cases = (
			(
				'/foo/bar/ -/foo/bar/*.foo -*.baz',
				(
					(
						'foo/bar/baz',
						True,
					),
					(
						'foo/bar/',
						True,
					),
					# /foo/bar/ does not match
					(
						'foo/bar',
						False,
					),
					# this is excluded
					(
						'foo/bar/baz.foo',
						False,
					),
					# this is excluded
					(
						'foo/bar/baz.baz',
						False,
					),
					(
						'foo/bar/baz.bar',
						True,
					),
				)
			),
			(
				'/foo/bar -/foo/bar/*.foo -*.baz',
				(
					(
						'foo/bar/baz',
						True,
					),
					# /foo/bar matches both foo/bar/ and foo/bar
					(
						'foo/bar/',
						True,
					),
					(
						'foo/bar',
						True,
					),
					# this is excluded
					(
						'foo/bar/baz.foo',
						False,
					),
					# this is excluded
					(
						'foo/bar/baz.baz',
						False,
					),
					(
						'foo/bar/baz.bar',
						True,
					),
				)
			),
			(
				'/foo*',
				(
					(
						'foo',
						True,
					),
					(
						'foo/',
						True,
					),
					(
						'foobar',
						True,
					),
					(
						'foobar/',
						True,
					),
				)
			),
			(
				'/foo*/',
				(
					(
						'foo',
						False,
					),
					(
						'foo/',
						True,
					),
					(
						'foobar',
						False,
					),
					(
						'foobar/',
						True,
					),
				)
			),
		)

		for install_mask_str, paths in cases:
			install_mask = InstallMask(install_mask_str)
			for path, expected in paths:
				self.assertEqual(install_mask.match(path), expected,
					'unexpected match result for "{}" with path {}'.\
					format(install_mask_str, path))
