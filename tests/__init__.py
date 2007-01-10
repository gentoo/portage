# tests/__init__.py -- Portage Unit Test functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import unittest

def main():
	
	testDirs = ["portage/", "portage_util/"]

	suite = unittest.TestSuite()

	for dir in testDirs:
		suite.addTests(getTests(dir))

	return unittest.TextTestRunner(verbosity=2).run(suite)

def getTests( path ):
	"""

	path is the path to a given subdir ( 'portage/' for example)
	This does a simple filter on files in that dir to give us modules
	to import

	"""
	import os
	files = os.listdir( path )
	files = [ f[:-3] for f in files if f.startswith("test_") and f.endswith(".py") ]

	result = []
	for file in files:
		try:
			# Make the trailing / a . for module importing
			path2 = path[:-1] + "." + file
			mod = __import__( path2, globals(), locals(), [path[-1]])
			result.append( unittest.TestLoader().loadTestsFromModule(mod) )
		except ImportError:
			pass
	return result
