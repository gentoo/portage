# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

anydbm_module = __import__("anydbm")
try:
	import cPickle as pickle
except ImportError:
	import pickle
import os
from cache import fs_template
from cache import cache_errors


class database(fs_template.FsBased):

	autocommits = True
	cleanse_keys = True
	serialize_eclasses = False

	def __init__(self, *args, **config):
		super(database,self).__init__(*args, **config)

		default_db = config.get("dbtype","anydbm")
		if not default_db.startswith("."):
			default_db = '.' + default_db

		self._db_path = os.path.join(self.location, fs_template.gen_label(self.location, self.label)+default_db)
		self.__db = None
		try:
			self.__db = anydbm_module.open(self._db_path, "w", self._perms)
				
		except anydbm_module.error:
			# XXX handle this at some point
			try:
				self._ensure_dirs()
				self._ensure_dirs(self._db_path)
			except (OSError, IOError), e:
				raise cache_errors.InitializationError(self.__class__, e)

			# try again if failed
			try:
				if self.__db == None:
					self.__db = anydbm_module.open(self._db_path, "c", self._perms)
			except anydbm_module.error, e:
				raise cache_errors.InitializationError(self.__class__, e)
		self._ensure_access(self._db_path)

	def iteritems(self):
		return self.__db.iteritems()

	def _getitem(self, cpv):
		# we override getitem because it's just a cpickling of the data handed in.
		return pickle.loads(self.__db[cpv])

	def _setitem(self, cpv, values):
		self.__db[cpv] = pickle.dumps(values,pickle.HIGHEST_PROTOCOL)

	def _delitem(self, cpv):
		del self.__db[cpv]

	def iterkeys(self):
		return iter(self.__db.keys())

	def __contains__(self, cpv):
		return cpv in self.__db

	def __del__(self):
		if "__db" in self.__dict__ and self.__db != None:
			self.__db.sync()
			self.__db.close()
