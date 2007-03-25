# config.py -- Portage Config
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
from UserDict import UserDict

class DataLoader(object):

	def load(self):
		"""
		Function to do the actual work of a Loader
		"""
		pass

class AtomFileLoader(DataLoader):
	"""
	Class to load data from a file full of atoms one per line
	
	>>> atom1
	>>> atom2
	>>> atom3
	
	becomes ['atom1', 'atom2', 'atom3']
	"""
	
	_recursive = False

	def __init__(self, filename):
		DataLoader.__init__(self)
		self.fname = filename
	
	def load(self):
                data = {}
                errors = {}
                line_count = 0
                file_list = None
                if self._recursive and os.path.isdir(self.fname):
                        for root, dirs, files in os.walk(self.fname):
                                if 'CVS' in dirs:
                                        dirs.remove('CVS')
                                files = filter(files,startswith('.'))
                                file_list.append([f.join(root,f) for f in files])
                else:
                        file_list = [self.fname]
		
		for file in file_list:
			f = open(file, 'rb')
			for line in f:
				line_count = line_count + 1
				if line.startswith('#'):
					continue
				split = line.strip().split()
				if not len(split):
					errors.setdefault(self.fname,[]).append(
					"Malformed data at line: %s, data: %s"
					% (line_count, split))
				key = split[0]
				data[key] = None			
		return (data,errors)

class KeyListFileLoader(DataLoader):
	"""
	Class to load data from a file full of key [list] tuples
	
	>>>>key foo1 foo2 foo3
	becomes
	{'key':['foo1','foo2','foo3']}
	"""

	_recursive = False

	def __init__(self, filename):
		DataLoader.__init__(self)
		self.fname = filename

	def load(self):
		data = {}
		errors = {}
		line_count = 0
		file_list = None
		if self._recursive and os.path.isdir(self.fname):
			for root, dirs, files in os.walk(self.fname):
				if 'CVS' in dirs:
					dirs.remove('CVS')
				files = filter(files,startswith('.'))
				file_list.append([f.join(root,f) for f in files])
		else:
			file_list = [self.fname]

		for file in file_list:
			f = open(file, 'rb')
			for line in f:
				line_count = line_count + 1
				if line.startswith('#'):
					continue
				split = line.strip().split()
				if len(split) < 2:
					errors.setdefault(self.fname,[]).append(
					"Malformed data at line: %s, data: %s"
					% (line_count, split))
				key = split[0]
				value = split[1:]
				if key in data:
					data[key].append(value)
				else:
					data[key] = value
		return (data,errors)

class KeyValuePairFileLoader(DataLoader):
	"""
	Class to load data from a file full of key=value pairs
	
	>>>>key=value
	>>>>foo=bar
	becomes:
	{'key':'value',
	 'foo':'bar'}
	"""

	_recursive = False

	def __init__(self, filename):
		DataLoader.__init__(self)
		self.fname = filename

	def load(self):
		"""
		Return the {source: {key: value}} pairs from a file
		Return the {source: [list of errors] from a load

		@param recursive: If set and self.fname is a directory; 
			load all files in self.fname
		@type: Boolean
		@rtype: tuple
		@returns:
		Returns (data,errors), both may be empty dicts or populated.
		"""

		DataLoader.load(self)
		data = {}
		errors = {}
		line_count = 0
                file_list = None
                if self._recursive and os.path.isdir(self.fname):
                        for root, dirs, files in os.walk(self.fname):
                                if 'CVS' in dirs:
                                        dirs.remove('CVS')
                                files = filter(files,startswith('.'))
                                file_list.append([f.join(root,f) for f in files])
                else:
                        file_list = [self.fname]

                for file in file_list:
			f = open(file, 'rb')
			for line in f:
				line_count = line_count + 1 # Increment line count
				if line.startswith('#'):
					continue
				split = line.strip().split('=')
				if len(split) < 2:
					errors.setdefault(self.fname,[]).append(
					"Malformed data at line: %s, data %s"
					% (line_count, split))
				key = split[0]
				value = split[1:]
				if key in data:
					data[key].append(value)
				else:
					data[key] = value
		return (data,errors)

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
		self.loader = self.default_loader(filename)
		PackageKeywords.__init__(self, self.loader)
	
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
		self.loader = self.default_loader(filename)
		PackageUse.__init__(self, self.loader)
	
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
	
	default_loader = KeyValuePairFileLoader

	def __init__(self, filename):
		self.loader = self.default_loader(filename)
		PackageMask.__init__(self, self.loader)
