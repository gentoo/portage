# test_normalizePath.py -- Portage Unit Testing Functionality
# Copyright 2006-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.tests import TestCase
from pathlib import Path

class NormalizePathTestCase(TestCase):

	def testNormalizePath(self):

		from portage.util import normalize_path
		path = Path("///foo/bar/baz")
		good = Path("/foo/bar/baz")
		self.assertEqual(normalize_path(path), good)
