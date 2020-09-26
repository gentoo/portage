# Copyright 2005-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# Author(s): Brian Harring (ferringb@gentoo.org)

import dbm

try:
	import dbm.gnu as gdbm
except ImportError:
	gdbm = None

import pickle

from portage import _unicode_encode
from portage import os
from portage.cache import fs_template
from portage.cache import cache_errors


class database(fs_template.FsBased):

	validation_chf = 'md5'
	chf_types = ('md5', 'mtime')

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
		mode = "w"
		if dbm.whichdb(self._db_path) in ("dbm.gnu", "gdbm"):
			# Allow multiple concurrent writers (see bug #53607).
			mode += "u"
		try:
			# dbm.open() will not work with bytes in python-3.1:
			#   TypeError: can't concat bytes to str
			self.__db = dbm.open(self._db_path,
				mode, self._perms)
		except dbm.error:
			# XXX handle this at some point
			try:
				self._ensure_dirs()
				self._ensure_dirs(self._db_path)
			except (OSError, IOError) as e:
				raise cache_errors.InitializationError(self.__class__, e)

			# try again if failed
			try:
				if self.__db == None:
					# dbm.open() will not work with bytes in python-3.1:
					#   TypeError: can't concat bytes to str
					if gdbm is None:
						self.__db = dbm.open(self._db_path,
							"c", self._perms)
					else:
						# Prefer gdbm type if available, since it allows
						# multiple concurrent writers (see bug #53607).
						self.__db = gdbm.open(self._db_path,
							"cu", self._perms)
			except dbm.error as e:
				raise cache_errors.InitializationError(self.__class__, e)
		self._ensure_access(self._db_path)

	def iteritems(self):
		# dbm doesn't implement items()
		for k in self.__db.keys():
			yield (k, self[k])

	def _getitem(self, cpv):
		# we override getitem because it's just a cpickling of the data handed in.
		return pickle.loads(self.__db[_unicode_encode(cpv)])

	def _setitem(self, cpv, values):
		self.__db[_unicode_encode(cpv)] = pickle.dumps(values,pickle.HIGHEST_PROTOCOL)

	def _delitem(self, cpv):
		del self.__db[cpv]

	def __iter__(self):
		return iter(list(self.__db.keys()))

	def __contains__(self, cpv):
		return cpv in self.__db

	def __del__(self):
		if "__db" in self.__dict__ and self.__db != None:
			self.__db.sync()
			self.__db.close()

	# TODO: do we need iteritems()?
	items = iteritems
