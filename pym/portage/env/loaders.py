# config.py -- Portage Config
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os

class LoaderError(Exception):
	
	def __init__(self, resource, error_msg):
		"""
		@param resource: Resource that failed to load (file/sql/etc)
		@type resource: String
		@param error_msg: Error from underlying Loader system
		@type error_msg: String
		"""

		self.resource
	
	def __str__(self):
		return "Failed while loading resource: %s, error was: %s" % (
			resource, error_msg)

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

	def __init__(self, validator=None):
		f = validator
		if f is None:
			# if they pass in no validator, just make a fake one
			# that always returns true
			class AlwaysTrue(object):
				def validate(self, key):
					return True
			f = AlwaysTrue()
		self._validator = f

	def load(self):
		"""
		Function to do the actual work of a Loader
		"""
		pass

class ItemFileLoader(DataLoader):
	"""
	Class to load data from a file full of items one per line
	
	>>> item1
	>>> item2
	>>> item3
	>>> item1
	
	becomes { 'item1':None, 'item2':None, 'item3':None }
	Note that due to the data store being a dict, duplicates
	are removed.
	"""
	
	_recursive = False

	def __init__(self, filename, validator):
		DataLoader.__init__(self, validator)
		self.fname = filename
	
	def load(self):
		data = {}
		errors = {}
		for file in RecursiveFileLoader(self.fname):
			f = open(file, 'rb')
			for line_num, line in enumerate(f):
				if line.startswith('#'):
					continue
				split = line.strip().split()
				if not len(split):
					errors.setdefault(self.fname,[]).append(
					"Malformed data at line: %s, data: %s"
					% (line_num + 1, split))
				key = split[0]
				if not self._validator.validate(key):
					errors.setdefault(self.fname,[]).append(
					"Validation failed at line: %s, data %s"
					% (line_num + 1, split))
					continue
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

	def __init__(self, filename, validator):
		DataLoader.__init__(self, validator)
		self.fname = filename

	def load(self):
		data = {}
		errors = {}
		for file in RecursiveFileLoader(self.fname):
			f = open(file, 'rb')
			for line_num, line in enumerate(f):
				if line.startswith('#'):
					continue
				split = line.strip().split()
				if len(split) < 2:
					errors.setdefault(self.fname,[]).append(
					"Malformed data at line: %s, data: %s"
					% (line_num + 1, split))
					continue
				key = split[0]
				value = split[1:]
				if not self._validator.validate(key):
					errors.setdefault(self.fname,[]).append(
					"Validation failed at line: %s, data %s"
					% (line_num + 1, split))
					continue
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

	def __init__(self, filename, validator):
		DataLoader.__init__(self, validator)
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
		for file in RecursiveFileLoader(self.fname):
			f = open(file, 'rb')
			for line_num, line in enumerate(f):
				if line.startswith('#'):
					continue
				split = line.strip().split('=')
				if len(split) < 2:
					errors.setdefault(self.fname,[]).append(
					"Malformed data at line: %s, data %s"
					% (line_num + 1, split))
				key = split[0]
				value = split[1:]
				if not self._validator.validate(key):
					errors.setdefault(self.fname,[]).append(
					"Validation failed at line: %s, data %s"
					% (line_num + 1, split))
					continue
				if key in data:
					data[key].append(value)
				else:
					data[key] = value
		return (data,errors)
