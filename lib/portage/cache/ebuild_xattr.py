# -*- coding: utf-8 -*-
# Copyright: 2009-2020 Gentoo Authors
# Author(s): Petteri Räty (betelgeuse@gentoo.org)
# License: GPL2

__all__ = ['database']

import errno

from portage.cache import fs_template
from portage.versions import catsplit
from portage import cpv_getkey
from portage import os
from portage import _encodings
from portage import _unicode_decode
from portage.util._xattr import xattr

class NoValueException(Exception):
	pass

class database(fs_template.FsBased):

	autocommits = True

	def __init__(self, *args, **config):
		super(database,self).__init__(*args, **config)
		self.portdir = self.label
		self.ns = xattr.NS_USER + '.gentoo.cache'
		self.keys = set(self._known_keys)
		self.keys.add('_mtime_')
		self.keys.add('_eclasses_')
		# xattrs have an upper length
		self.max_len = self.__get_max()

	def __get_max(self):
		path = os.path.join(self.portdir,'profiles/repo_name')
		try:
			return int(self.__get(path,'value_max_len'))
		except NoValueException as e:
			maxattrlength = self.__calc_max(path)
			self.__set(path, 'value_max_len', str(maxattrlength))
			return maxattrlength

	def __calc_max(self,path):
		""" Find out max attribute length supported by the file system """

		hundred = ''
		for i in range(100):
			hundred+='a'

		s=hundred

		# Could use finally but needs python 2.5 then
		try:
			while True:
				self.__set(path,'test_max',s)
				s+=hundred
		except IOError as e:
			# ext based give wrong errno
			# https://bugzilla.kernel.org/show_bug.cgi?id=12793
			if e.errno in (errno.E2BIG, errno.ENOSPC):
				result = len(s)-100
			else:
				raise

		try:
			self.__remove(path,'test_max')
		except IOError as e:
			if e.errno != errno.ENODATA:
				raise

		return result

	def __get_path(self,cpv):
		cat,pn = catsplit(cpv_getkey(cpv))
		return os.path.join(self.portdir,cat,pn,os.path.basename(cpv) + ".ebuild")

	def __has_cache(self,path):
		try:
			self.__get(path,'_mtime_')
		except NoValueException as e:
			return False

		return True

	def __get(self,path,key,default=None):
		try:
			return xattr.get(path,key,namespace=self.ns)
		except IOError as e:
			if not default is None and errno.ENODATA == e.errno:
				return default
			raise NoValueException()

	def __remove(self,path,key):
		xattr.remove(path,key,namespace=self.ns)

	def __set(self,path,key,value):
		xattr.set(path,key,value,namespace=self.ns)

	def _getitem(self, cpv):
		values = {}
		path = self.__get_path(cpv)
		attrs = {
			key: value
			for key, value in xattr.get_all(path, namespace=self.ns)
		}

		if not '_mtime_' in all:
			raise KeyError(cpv)

		# We default to '' like other caches
		for key in self.keys:
			attr_value = attrs.get(key,'1:')
			parts,sep,value = attr_value.partition(':')
			parts = int(parts)
			if parts > 1:
				for i in range(1,parts):
					value += attrs.get(key+str(i))
			values[key] = value

		return values

	def _setitem(self, cpv, values):
		path = self.__get_path(cpv)
		max_len = self.max_len
		for key,value in values.items():
			# mtime comes in as long so need to convert to strings
			s = str(value)
			# We need to split long values
			value_len = len(s)
			parts = 0
			if value_len > max_len:
				# Find out how many parts we need
				parts = value_len/max_len
				if value_len % max_len > 0:
					parts += 1

				# Only the first entry carries the number of parts
				self.__set(path,key,'%s:%s'%(parts,s[0:max_len]))

				# Write out the rest
				for i in range(1,parts):
					start = i * max_len
					val = s[start:start+max_len]
					self.__set(path,key+str(i),val)
			else:
				self.__set(path,key,"%s:%s"%(1,s))

	def _delitem(self, cpv):
		pass # Will be gone with the ebuild

	def __contains__(self, cpv):
		return os.path.exists(self.__get_path(cpv))

	def __iter__(self):

		for root, dirs, files in os.walk(self.portdir):
			for file in files:
				try:
					file = _unicode_decode(file,
						encoding=_encodings['fs'], errors='strict')
				except UnicodeDecodeError:
					continue
				if file[-7:] == '.ebuild':
					cat = os.path.basename(os.path.dirname(root))
					pn_pv = file[:-7]
					path = os.path.join(root,file)
					if self.__has_cache(path):
						yield "%s/%s/%s" % (cat,os.path.basename(root),file[:-7])
