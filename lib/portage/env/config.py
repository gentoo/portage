# config.py -- Portage Config
# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["ConfigLoaderKlass", "GenericFile", "PackageKeywordsFile",
	"PackageUseFile", "PackageMaskFile", "PortageModulesFile"]

from portage.cache.mappings import UserDict
from portage.env.loaders import KeyListFileLoader, KeyValuePairFileLoader, ItemFileLoader

class ConfigLoaderKlass(UserDict):
	"""
	A base class stub for things to inherit from.
	Users may want a non-file backend.
	"""

	def __init__(self, loader):
		"""
		@param loader: A class that has a load() that returns two dicts
			the first being a data dict, the second being a dict of errors.
		"""
		UserDict.__init__(self)
		self._loader = loader

	def load(self):
		"""
		Load the data from the loader.

		@throws LoaderError:
		"""

		self.data, self.errors = self._loader.load()

class GenericFile(UserDict):
	"""
	Inherits from ConfigLoaderKlass, attempts to use all known loaders
	until it gets <something> in data.  This is probably really slow but is
	helpful when you really have no idea what you are loading (hint hint the file
	should perhaps declare  what type it is? ;)
	"""

	loaders = [KeyListFileLoader, KeyValuePairFileLoader, ItemFileLoader]

	def __init__(self, filename):
		UserDict.__init__(self)
		self.filename = filename

	def load(self):
		for loader in self.loaders:
			l = loader(self.filename, None)
			data, errors = l.load()
			if len(data) and not len(errors):
				(self.data, self.errors) = (data, errors)
				return


class PackageKeywordsFile(ConfigLoaderKlass):
	"""
	Inherits from ConfigLoaderKlass; implements a file-based backend.
	"""

	default_loader = KeyListFileLoader

	def __init__(self, filename):
		super(PackageKeywordsFile, self).__init__(
			self.default_loader(filename, validator=None))

class PackageUseFile(ConfigLoaderKlass):
	"""
	Inherits from PackageUse; implements a file-based backend.  Doesn't handle recursion yet.
	"""

	default_loader = KeyListFileLoader
	def __init__(self, filename):
		super(PackageUseFile, self).__init__(
			self.default_loader(filename, validator=None))

class PackageMaskFile(ConfigLoaderKlass):
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

class PortageModulesFile(ConfigLoaderKlass):
	"""
	File Class for /etc/portage/modules
	"""

	default_loader = KeyValuePairFileLoader

	def __init__(self, filename):
		super(PortageModulesFile, self).__init__(
			 self.default_loader(filename, validator=None))
