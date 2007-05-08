# config.py -- Portage Config
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

from UserDict import UserDict
from portage.env.loaders import KeyListFileLoader, KeyValuePairFileLoader, ItemFileLoader

class UserConfigKlass(UserDict,object):
	"""
	A base class stub for things to inherit from.
	Users may want a non-file backend.
	"""
	
	data = {}
	
	def __init__(self, loader):
		"""
		@param loader: A class that has a load() that returns two dicts
			the first being a data dict, the second being a dict of errors.
		"""
		self._loader = loader

	def load(self):
		"""
		Load the data from the loader.

		@throws LoaderError:
		"""

		self.data, self.errors = self._loader.load()

class PackageKeywordsFile(UserConfigKlass):
	"""
	Inherits from UserConfigKlass; implements a file-based backend.
	"""

	default_loader = KeyListFileLoader

	def __init__(self, filename):
		super(PackageKeywordsFile, self).__init__(
			self.default_loader(filename, validator=None))
	
class PackageUseFile(UserConfigKlass):
	"""
	Inherits from PackageUse; implements a file-based backend.  Doesn't handle recursion yet.
	"""

	default_loader = KeyListFileLoader
	def __init__(self, filename):
		super(PackageUseFile, self).__init__(
			self.default_loader(filename, validator=None))
	
class PackageMaskFile(UserConfigKlass):
	"""
	A class that implements a file-based package.mask
	
	Entires in package.mask are of the form:
	atom1
	atom2
	or optionally
	-atom3
	to revert a previous mask; this only works when masking files are stacked
	"""
	
	default_loader = ItemFileLoader

	def __init__(self, filename):
		super(PackageMaskFile, self).__init__(
			self.default_loader(filename, validator=None))

class PortageModulesFile(UserConfigKlass):
	"""
	File Class for /etc/portage/modules
	"""
	
	default_loader = KeyValuePairFileLoader
	
	def __init__(self, filename):
		super(PortageModulesFile, self).__init__(
			 self.default_loader(filename, validator=None))
