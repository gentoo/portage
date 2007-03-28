# config.py -- Portage Config
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os

def RecursiveFileLoader(filename):
	"""
	If filename is of type file, return [filename]
	else if filename is of type directory, return an array
	full of files in that directory to process.
	
	Ignore files beginning with . or ending in ~.
	Prune CVS directories.	

	@param filename: name of a file/directory to traverse
	@rtype: list
	@returns: List of files to process
	"""

	if os.path.isdir(filename):
		for root, dirs, files in os.walk(self.fname):
			if 'CVS' in dirs:
				dirs.remove('CVS')
			files = filter(files,startswith('.'))
			files = filter(files,endswith('~'))
			for file in files:
				yield file
	else:
		yield filename

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
		for file in RecursiveFileLoader(self.fname):
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
		for file in RecursiveFileLoader(self.fname):
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
                for file in RecursiveFileLoader(self.fname):
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
