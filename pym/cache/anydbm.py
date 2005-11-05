# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: anydbm.py 1911 2005-08-25 03:44:21Z ferringb $

anydbm_module = __import__("anydbm")
try:
	import cPickle as pickle
except ImportError:
	import pickle
import os
import fs_template
import cache_errors


class database(fs_template.FsBased):

	autocommits = True
	cleanse_keys = True

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
				self._ensure_access(self._db_path)
			except (OSError, IOError), e:
				raise cache_errors.InitializationError(self.__class__, e)

			# try again if failed
			try:
				if self.__db == None:
					self.__db = anydbm_module.open(self._db_path, "c", self._perms)
			except andbm_module.error, e:
				raise cache_errors.InitializationError(self.__class__, e)

	def iteritems(self):
		return self.__db.iteritems()

	def __getitem__(self, cpv):
		# we override getitem because it's just a cpickling of the data handed in.
		return pickle.loads(self.__db[cpv])


	def _setitem(self, cpv, values):
		self.__db[cpv] = pickle.dumps(values,pickle.HIGHEST_PROTOCOL)

	def _delitem(self, cpv):
		del self.__db[cpv]


	def iterkeys(self):
		return iter(self.__db)


	def has_key(self, cpv):
		return cpv in self.__db


	def __del__(self):
		if "__db" in self.__dict__ and self.__db != None:
			self.__db.sync()
			self.__db.close()
