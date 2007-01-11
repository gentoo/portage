# tests/__init__.py -- Portage Unit Test functionality
# Copyright 2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os, unittest

def main():
	
	testDirs = ["portage", "portage_util","portage_versions"]

	suite = unittest.TestSuite()

	basedir = os.path.dirname(__file__)
	for mydir in testDirs:
		suite.addTests(getTests(os.path.join(basedir, mydir), basedir) )

	return unittest.TextTestRunner(verbosity=2).run(suite)

def my_import(name):
	mod = __import__(name)
	components = name.split('.')
	for comp in components[1:]:
		mod = getattr(mod, comp)
	return mod

def getTests( path, base_path ):
	"""

	path is the path to a given subdir ( 'portage/' for example)
	This does a simple filter on files in that dir to give us modules
	to import

	"""
	import os
	files = os.listdir( path )
	files = [ f[:-3] for f in files if f.startswith("test_") and f.endswith(".py") ]
	parent_path = path[len(base_path):]
	parent_module = ".".join(("tests", parent_path))
	result = []
	for mymodule in files:
		try:
			# Make the trailing / a . for module importing
			modname = ".".join((parent_module, mymodule))
			mod = my_import(modname)
			result.append( unittest.TestLoader().loadTestsFromModule(mod) )
		except ImportError:
			raise
	return result
