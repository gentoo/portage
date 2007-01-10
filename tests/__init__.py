# tests/__init__.py -- Portage Unit Test functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import unittest

def main():
	
	tests = ["test_atoms", "test_util"]

	suite = unittest.TestSuite()

	for mod in tests:
		try:
			loadMod = __import__(mod)
			tmpSuite = unittest.TestLoader().loadTestsFromModule(loadMod)
			suite.addTest(tmpSuite)
		except ImportError:
			pass

	return unittest.TextTestRunner(verbosity=2).run(suite)
