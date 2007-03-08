# config.py -- Portage Config
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import os
from UserDict import UserDict

class PackageKeywords(UserDict):
	"""
	A base class stub for things to inherit from; some people may want a database based package.keywords or something
	
	Internally dict has pairs of the form
	{'cpv':['keyword1','keyword2','keyword3'...]
	"""
	
	data = {}
	
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
	def __init__( self, filename ):
		self.fname = filename
	
	def load(self, recursive):
		"""
		Package.keywords files have comments that begin with #.
		The entries are of the form:
		>>> cpv [-~]keyword1 [-~]keyword2 keyword3
		>>> Exceptions include -*, ~*, and ** for keywords.
		"""
		
		if os.path.exists( self.fname ):
			f = open(self.fname, 'rb')
			for line in f:
				if line.startswith('#'):
					continue
				split = line.split()
				if len(split):
					# Surprisingly this works for iterables of length 1
					# fex ['sys-apps/portage','x86','amd64'] becomes {'sys-apps/portage':['x86','amd64']}
					key, items = split[0],split[1:]
					# if they specify the same cpv twice; stack the values (append) instead of overwriting.
					if key in self.data:
						self.data[key].append(items)
					else:
						self.data[key] = items

class PackageUse(UserDict):
	"""
	A base class stub for things to inherit from; some people may want a database based package.keywords or something
	
	Internally dict has pairs of the form
	{'cpv':['flag1','flag22','flag3'...]
	"""
	
	data = {}
	
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
	def __init__(self, filename):
		self.fname = filename
	
	def load(self, recursive):
		"""
		Package.keywords files have comments that begin with #.
		The entries are of the form:
		>>> atom useflag1 useflag2 useflag3..
		useflags may optionally be negative with a minus sign (-)
		>>> atom useflag1 -useflag2 useflag3
		"""
		
		if os.path.exists( self.fname ):
			f = open(self.fname, 'rb')
			for line in f:
				if line.startswith('#'):
					continue
				split = line.split()
				if len(split):
					# Surprisingly this works for iterables of length 1
					# fex ['sys-apps/portage','foo','bar'] becomes {'sys-apps/portage':['foo','bar']}
					key, items = split[0],split[1:]
					# if they specify the same cpv twice; stack the values (append) instead of overwriting.
					if key in self.data:
						self.data[key].append(items)
					else:
						self.data[key] = items

class PackageMask(UserDIct):
	"""
	A base class for Package.mask functionality
	"""
	data = {}
	
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
	
	def __init__(self, filename):
		self.fname = filename
	
	def load(self, recursive):
		"""
		Package.keywords files have comments that begin with #.
		The entries are of the form:
		>>> atom useflag1 useflag2 useflag3..
		useflags may optionally be negative with a minus sign (-)
		>>> atom useflag1 -useflag2 useflag3
		"""
		
		if os.path.exists( self.fname ):
			f = open(self.fname, 'rb')
			for line in f:
				if line.startswith('#'):
					continue
				split = line.split()
				if len(split):
					atom = split[0] # This is an extra assignment, but I think it makes the code more explicit in what goes into the dict
					self.data[atom] = None # we only care about keys in the dict, basically abusing it as a list
