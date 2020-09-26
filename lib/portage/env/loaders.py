# config.py -- Portage Config
# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import errno
import io
import stat
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util:writemsg',
)
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage import _unicode_encode
from portage.localization import _

class LoaderError(Exception):

	def __init__(self, resource, error_msg):
		"""
		@param resource: Resource that failed to load (file/sql/etc)
		@type resource: String
		@param error_msg: Error from underlying Loader system
		@type error_msg: String
		"""

		self.resource = resource
		self.error_msg = error_msg

	def __str__(self):
		return "Failed while loading resource: %s, error was: %s" % (
			self.resource, self.error_msg)


def RecursiveFileLoader(filename):
	"""
	If filename is of type file, return a generate that yields filename
	else if filename is of type directory, return a generator that fields
	files in that directory.

	Ignore files beginning with . or ending in ~.
	Prune CVS directories.

	@param filename: name of a file/directory to traverse
	@rtype: list
	@return: List of files to process
	"""

	try:
		st = os.stat(filename)
	except OSError:
		return
	if stat.S_ISDIR(st.st_mode):
		for root, dirs, files in os.walk(filename):
			for d in list(dirs):
				if d[:1] == '.' or d == 'CVS':
					dirs.remove(d)
			for f in files:
				try:
					f = _unicode_decode(f,
						encoding=_encodings['fs'], errors='strict')
				except UnicodeDecodeError:
					continue
				if f[:1] == '.' or f[-1:] == '~':
					continue
				yield os.path.join(root, f)
	else:
		yield filename


class DataLoader:

	def __init__(self, validator):
		f = validator
		if f is None:
			# if they pass in no validator, just make a fake one
			# that always returns true
			def validate(key):
				return True
			f = validate
		self._validate = f

	def load(self):
		"""
		Function to do the actual work of a Loader
		"""
		raise NotImplementedError("Please override in a subclass")

class EnvLoader(DataLoader):
	""" Class to access data in the environment """
	def __init__(self, validator):
		DataLoader.__init__(self, validator)

	def load(self):
		return os.environ

class TestTextLoader(DataLoader):
	""" You give it some data, it 'loads' it for you, no filesystem access
	"""
	def __init__(self, validator):
		DataLoader.__init__(self, validator)
		self.data = {}
		self.errors = {}

	def setData(self, text):
		"""Explicitly set the data field
		Args:
			text - a dict of data typical of Loaders
		Returns:
			None
		"""
		if isinstance(text, dict):
			self.data = text
		else:
			raise ValueError("setData requires a dict argument")

	def setErrors(self, errors):
		self.errors = errors

	def load(self):
		return (self.data, self.errors)


class FileLoader(DataLoader):
	""" Class to access data in files """

	def __init__(self, filename, validator):
		"""
			Args:
				filename : Name of file or directory to open
				validator : class with validate() method to validate data.
		"""
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
		@return:
		Returns (data,errors), both may be empty dicts or populated.
		"""
		data = {}
		errors = {}
		# I tried to save a nasty lookup on lineparser by doing the lookup
		# once, which may be expensive due to digging in child classes.
		func = self.lineParser
		for fn in RecursiveFileLoader(self.fname):
			try:
				with io.open(_unicode_encode(fn,
					encoding=_encodings['fs'], errors='strict'), mode='r',
					encoding=_encodings['content'], errors='replace') as f:
					lines = f.readlines()
			except EnvironmentError as e:
				if e.errno == errno.EACCES:
					writemsg(_("Permission denied: '%s'\n") % fn, noiselevel=-1)
					del e
				elif e.errno in (errno.ENOENT, errno.ESTALE):
					del e
				else:
					raise
			else:
				for line_num, line in enumerate(lines):
					func(line, line_num, data, errors)
		return (data, errors)

	def lineParser(self, line, line_num, data, errors):
		""" This function parses 1 line at a time
			Args:
				line: a string representing 1 line of a file
				line_num: an integer representing what line we are processing
				data: a dict that contains the data we have extracted from the file
				      already
				errors: a dict representing parse errors.
			Returns:
				Nothing (None).  Writes to data and errors
		"""
		raise NotImplementedError("Please over-ride this in a child class")

class ItemFileLoader(FileLoader):
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

	def __init__(self, filename, validator):
		FileLoader.__init__(self, filename, validator)

	def lineParser(self, line, line_num, data, errors):
		line = line.strip()
		if line.startswith('#'): # Skip commented lines
			return
		if not len(line): # skip empty lines
			return
		split = line.split()
		if not len(split):
			errors.setdefault(self.fname, []).append(
				_("Malformed data at line: %s, data: %s")
				% (line_num + 1, line))
			return
		key = split[0]
		if not self._validate(key):
			errors.setdefault(self.fname, []).append(
				_("Validation failed at line: %s, data %s")
				% (line_num + 1, key))
			return
		data[key] = None

class KeyListFileLoader(FileLoader):
	"""
	Class to load data from a file full of key [list] tuples

	>>>>key foo1 foo2 foo3
	becomes
	{'key':['foo1','foo2','foo3']}
	"""

	def __init__(self, filename, validator=None, valuevalidator=None):
		FileLoader.__init__(self, filename, validator)

		f = valuevalidator
		if f is None:
			# if they pass in no validator, just make a fake one
			# that always returns true
			def validate(key):
				return True
			f = validate
		self._valueValidate = f

	def lineParser(self, line, line_num, data, errors):
		line = line.strip()
		if line.startswith('#'): # Skip commented lines
			return
		if not len(line): # skip empty lines
			return
		split = line.split()
		if len(split) < 1:
			errors.setdefault(self.fname, []).append(
				_("Malformed data at line: %s, data: %s")
				% (line_num + 1, line))
			return
		key = split[0]
		value = split[1:]
		if not self._validate(key):
			errors.setdefault(self.fname, []).append(
				_("Key validation failed at line: %s, data %s")
				% (line_num + 1, key))
			return
		if not self._valueValidate(value):
			errors.setdefault(self.fname, []).append(
				_("Value validation failed at line: %s, data %s")
				% (line_num + 1, value))
			return
		if key in data:
			data[key].append(value)
		else:
			data[key] = value


class KeyValuePairFileLoader(FileLoader):
	"""
	Class to load data from a file full of key=value pairs

	>>>>key=value
	>>>>foo=bar
	becomes:
	{'key':'value',
	 'foo':'bar'}
	"""

	def __init__(self, filename, validator, valuevalidator=None):
		FileLoader.__init__(self, filename, validator)

		f = valuevalidator
		if f is None:
			# if they pass in no validator, just make a fake one
			# that always returns true
			def validate(key):
				return True
			f = validate
		self._valueValidate = f


	def lineParser(self, line, line_num, data, errors):
		line = line.strip()
		if line.startswith('#'): # skip commented lines
			return
		if not len(line): # skip empty lines
			return
		split = line.split('=', 1)
		if len(split) < 2:
			errors.setdefault(self.fname, []).append(
				_("Malformed data at line: %s, data %s")
				% (line_num + 1, line))
			return
		key = split[0].strip()
		value = split[1].strip()
		if not key:
			errors.setdefault(self.fname, []).append(
				_("Malformed key at line: %s, key %s")
				% (line_num + 1, key))
			return
		if not self._validate(key):
			errors.setdefault(self.fname, []).append(
				_("Key validation failed at line: %s, data %s")
				% (line_num + 1, key))
			return
		if not self._valueValidate(value):
			errors.setdefault(self.fname, []).append(
				_("Value validation failed at line: %s, data %s")
				% (line_num + 1, value))
			return
		data[key] = value
