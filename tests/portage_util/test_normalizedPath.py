# test_normalizePath.py -- Portage Unit Testing Functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_vercmp.py 5213 2006-12-08 00:12:41Z antarus $

from unittest import TestCase

class NormalizePathTestCase(TestCase):
	
	def testNormalizePath(self):
		
		from portage_util import normalize_path
		path = "///foo/bar/baz"
		good = "/foo/bar/baz"
		self.failUnless(normalize_path(path) == good, msg="NormalizePath(%s) failed to produce %s" % (path, good))

