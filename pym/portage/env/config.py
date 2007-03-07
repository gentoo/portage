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
	{'cpv':['key1','key2','key3'...]
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
	
	def load(self, recursive=False):
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
