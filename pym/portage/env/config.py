# config.py -- Portage Config
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from UserDict import UserDict
from portage.env.loaders import KeyListFileLoader, KeyValuePairFileLoader, AtomFileLoader

class PackageKeywords(UserDict):
	"""
	A base class stub for things to inherit from; some people may want a database based package.keywords or something
	
	Internally dict has pairs of the form
	{'cpv':['keyword1','keyword2','keyword3'...]
	"""
	
	data = {}
	
	def __init__(self, loader):
		self._loader = loader

	def load(self):
		self.data, self.errors = self._loader.load()

	def iteritems(self):
		return self.data.iteritems()
	
	def keys(self):
		return self.data.keys()
	
	def __contains__(self, other):
		return other in self.data
	
	def __hash__( self ):
		return self.data.__hash__()
	
class PackageKeywordsFile(PackageKeywords):
	"""
	Inherits from PackageKeywords; implements a file-based backend.  Doesn't handle recursion yet.
	"""

	default_loader = KeyListFileLoader

	def __init__(self, filename):
		PackageKeywords.__init__(self, self.default_loader(filename))
	
class PackageUse(UserDict):
	"""
	A base class stub for things to inherit from; some people may want a database based package.keywords or something
	
	Internally dict has pairs of the form
	{'cpv':['flag1','flag22','flag3'...]
	"""
	
	data = {}
	
	def __init__(self, loader):
		self._loader = loader

	def load( self):
		self.data, self.errors = self._loader.load()

	def iteritems(self):
		return self.data.iteritems()
	
	def __hash__(self):
		return hash(self.data)
	
	def __contains__(self, other):
		return other in self.data
	
	def keys(self):
		return self.data.keys()

class PackageUseFile(PackageUse):
	"""
	Inherits from PackageUse; implements a file-based backend.  Doesn't handle recursion yet.
	"""

	default_loader = KeyListFileLoader
	def __init__(self, filename):
		PackageUse.__init__(self, self.default_loader(filename))
	
class PackageMask(UserDict):
	"""
	A base class for Package.mask functionality
	"""
	data = {}
	
	def __init__(self, loader):
		self._loader = loader
	
	def load(self):
		self.data, self.errors = self._loader.load()
		
	def iteritems(self):
		return self.data.iteritems()
	
	def __hash__(self):
		return hash(self.data)
	
	def __contains__(self, other):
		return other in self.data
	
	def keys(self):
		return self.data.keys()
	
	def iterkeys(self):
		return self.data.iterkeys()

class PackageMaskFile(PackageMask):
	"""
	A class that implements a file-based package.mask
	
	Entires in package.mask are of the form:
	atom1
	atom2
	or optionally
	-atom3
	to revert a previous mask; this only works when masking files are stacked
	"""
	
	default_loader = AtomFileLoader

	def __init__(self, filename):
		PackageMask.__init__(self, self.default_loader(filename))

class PortageModules(UserDict):
	"""
	Base Class for user level module over-rides
	"""
	
	data = {}

	def __init__(self, loader):
		self._loader = loader

	def load(self):
		self.data, self.errors = self._loader.load()

	def iteritems(self):
		return self.data.iteritems()
	
	def __hash__(self):
		return self.data.__hash__()

	def __contains__(self, key):
		return key in self.data

	def keys(self):
		return self.data.keys()
	
	def iterkeys(self):
		return self.data.iterkeys()

class PortageModulesFile(PortageModules):
	"""
	File Class for /etc/portage/modules
	"""
	
	default_loader = KeyValuePairFileLoader
	
	def __init__(self, filename):
		PortageModules.__init__(self, self.default_loader(filename))
