# tests/__init__.py -- Portage Unit Test functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import unittest

def main():
	
	tests = ["test_vercmp", "test_util"]

	suite = unittest.TestSuite()

	for mod in tests:
		try:
			test_mod = __import__(mod)
			suite.addTest(test_mod.suite())
		except ImportError:
			pass

	return unittest.TextTestRunner(verbosity=2).run(suite)
