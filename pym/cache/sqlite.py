# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

from cache import fs_template
from cache import cache_errors
import errno, os, stat
from cache.mappings import LazyLoad, ProtectedDict
from cache.template import reconstruct_eclasses
from portage_util import writemsg, apply_secpass_permissions
from portage_data import portage_gid
try:
	import sqlite3 as db_module # sqlite3 is optional with >=python-2.5
except ImportError:
	from pysqlite2 import dbapi2 as db_module
DBError = db_module.Error

class database(fs_template.FsBased):

	autocommits = False
	synchronous = False
	# cache_bytes is used together with page_size (set at sqlite build time)
	# to calculate the number of pages requested, according to the following
	# equation: cache_bytes = page_bytes * page_count
	cache_bytes = 1024 * 1024 * 10
	_db_module = db_module
	_db_error = DBError
	_db_table = None

	def __init__(self, *args, **config):
		super(database, self).__init__(*args, **config)
		self._allowed_keys = ["_mtime_", "_eclasses_"] + self._known_keys
		self.location = os.path.join(self.location, 
			self.label.lstrip(os.path.sep).rstrip(os.path.sep))

		if not os.path.exists(self.location):
			self._ensure_dirs()

		config.setdefault("autocommit", self.autocommits)
		config.setdefault("cache_bytes", self.cache_bytes)
		config.setdefault("synchronous", self.synchronous)
		self._db_init_connection(config)
		self._db_init_structures()

	def _db_escape_string(self, s):
		"""meta escaping, returns quoted string for use in sql statements"""
		return "'%s'" % str(s).replace("\\","\\\\").replace("'","''")

	def _db_init_connection(self, config):
		self._dbpath = self.location + ".sqlite"
		#if os.path.exists(self._dbpath):
		#	os.unlink(self._dbpath)
		try:
			self._ensure_dirs()
			self._db_connection = self._db_module.connect(database=self._dbpath)
			self._db_cursor = self._db_connection.cursor()
			self._db_cursor.execute("PRAGMA encoding = %s" % self._db_escape_string("UTF-8"))
			if not apply_secpass_permissions(self._dbpath, gid=portage_gid, mode=070, mask=02):
				raise cache_errors.InitializationError(self.__class__, "can't ensure perms on %s" % self._dbpath)
			self._db_init_cache_size(config["cache_bytes"])
			self._db_init_synchronous(config["synchronous"])
		except self._db_error, e:
			raise cache_errors.InitializationError(self.__class__, e)

	def _db_init_structures(self):
		self._db_table = {}
		self._db_table["packages"] = {}
		mytable = "portage_packages"
		self._db_table["packages"]["table_name"] = mytable
		self._db_table["packages"]["package_id"] = "internal_db_package_id"
		self._db_table["packages"]["package_key"] = "portage_package_key"
		self._db_table["packages"]["internal_columns"] = \
			[self._db_table["packages"]["package_id"],
			self._db_table["packages"]["package_key"]]
		create_statement = []
		create_statement.append("CREATE TABLE")
		create_statement.append(mytable)
		create_statement.append("(")
		table_parameters = []
		table_parameters.append("%s INTEGER PRIMARY KEY AUTOINCREMENT" % self._db_table["packages"]["package_id"])
		table_parameters.append("%s TEXT" % self._db_table["packages"]["package_key"])
		for k in self._allowed_keys:
			table_parameters.append("%s TEXT" % k)
		table_parameters.append("UNIQUE(%s)" % self._db_table["packages"]["package_key"])
		create_statement.append(",".join(table_parameters))
		create_statement.append(")")
		
		self._db_table["packages"]["create"] = " ".join(create_statement)
		self._db_table["packages"]["columns"] = \
			self._db_table["packages"]["internal_columns"] + \
			self._allowed_keys

		cursor = self._db_cursor
		for k, v in self._db_table.iteritems():
			if self._db_table_exists(v["table_name"]):
				create_statement = self._db_table_get_create(v["table_name"])
				if create_statement != v["create"]:
					writemsg("sqlite: dropping old table: %s\n" % v["table_name"])
					cursor.execute("DROP TABLE %s" % v["table_name"])
					cursor.execute(v["create"])
			else:
				cursor.execute(v["create"])

	def _db_table_exists(self, table_name):
		"""return true/false dependant on a tbl existing"""
		cursor = self._db_cursor
		cursor.execute("SELECT name FROM sqlite_master WHERE type=\"table\" AND name=%s" % \
			self._db_escape_string(table_name))
		return len(cursor.fetchall()) == 1

	def _db_table_get_create(self, table_name):
		"""return true/false dependant on a tbl existing"""
		cursor = self._db_cursor
		cursor.execute("SELECT sql FROM sqlite_master WHERE name=%s" % \
			self._db_escape_string(table_name))
		return cursor.fetchall()[0][0]

	def _db_init_cache_size(self, cache_bytes):
		cursor = self._db_cursor
		cursor.execute("PRAGMA page_size")
		page_size=int(cursor.fetchone()[0])
		# number of pages, sqlite default is 2000
		cache_size = cache_bytes / page_size
		cursor.execute("PRAGMA cache_size = %d" % cache_size)
		cursor.execute("PRAGMA cache_size")
		actual_cache_size = int(cursor.fetchone()[0])
		del cursor
		if actual_cache_size != cache_size:
			raise cache_errors.InitializationError(self.__class__,"actual cache_size = "+actual_cache_size+" does does not match requested size of "+cache_size)

	def _db_init_synchronous(self, synchronous):
		cursor = self._db_cursor
		cursor.execute("PRAGMA synchronous = %d" % synchronous)
		cursor.execute("PRAGMA synchronous")
		actual_synchronous=int(cursor.fetchone()[0])
		del cursor
		if actual_synchronous!=synchronous:
			raise cache_errors.InitializationError(self.__class__,"actual synchronous = "+actual_synchronous+" does does not match requested value of "+synchronous)

	def __getitem__(self, cpv):
		if not self.has_key(cpv):
			raise KeyError(cpv)
		def curry(*args):
			def callit(*args2):
				return args[0](*args[1:]+args2)
			return callit
		return ProtectedDict(LazyLoad(curry(self._pull, cpv)))

	def _pull(self, cpv):
		cursor = self._db_cursor
		cursor.execute("select * from %s where %s=%s" % \
			(self._db_table["packages"]["table_name"],
			self._db_table["packages"]["package_key"],
			self._db_escape_string(cpv)))
		result = cursor.fetchall()
		if len(result) == 1:
			pass
		elif len(result) == 0:
			raise KeyError(cpv)
		else:
			raise cache_errors.CacheCorruption(cpv, "key is not unique")
		d = {}
		internal_columns = self._db_table["packages"]["internal_columns"]
		column_index = -1
		for k in self._db_table["packages"]["columns"]:
			column_index +=1
			if k not in internal_columns:
				d[k] = result[0][column_index]
		# XXX: The resolver chokes on unicode strings so we convert them here.
		for k in d.keys():
			try:
				d[k]=str(d[k]) # convert unicode strings to normal
			except UnicodeEncodeError, e:
				pass #writemsg("%s: %s\n" % (cpv, str(e)))
		if "_eclasses_" in d:
			d["_eclasses_"] = reconstruct_eclasses(cpv, d["_eclasses_"])
		for x in self._known_keys:
			d.setdefault(x,'')
		return d

	def _setitem(self, cpv, values):
		update_statement = []
		update_statement.append("REPLACE INTO %s" % self._db_table["packages"]["table_name"])
		update_statement.append("(")
		update_statement.append(','.join([self._db_table["packages"]["package_key"]] + self._allowed_keys))
		update_statement.append(")")
		update_statement.append("VALUES")
		update_statement.append("(")
		values_parameters = []
		values_parameters.append(self._db_escape_string(cpv))
		for k in self._allowed_keys:
			values_parameters.append(self._db_escape_string(values.get(k, '')))
		update_statement.append(",".join(values_parameters))
		update_statement.append(")")
		cursor = self._db_cursor
		try:
			s = " ".join(update_statement)
			cursor.execute(s)
		except self._db_error, e:
			writemsg("%s: %s\n" % (cpv, str(e)))
			raise

	def commit(self):
		self._db_connection.commit()

	def _delitem(self, cpv):
		cursor = self._db_cursor
		cursor.execute("DELETE FROM %s WHERE %s=%s" % \
			(self._db_table["packages"]["table_name"],
			self._db_table["packages"]["package_key"],
			self._db_escape_string(cpv)))

	def has_key(self, cpv):
		cursor = self._db_cursor
		cursor.execute(" ".join(
			["SELECT %s FROM %s" %
			(self._db_table["packages"]["package_id"],
			self._db_table["packages"]["table_name"]),
			"WHERE %s=%s" % (
			self._db_table["packages"]["package_key"],
			self._db_escape_string(cpv))]))
		result = cursor.fetchall()
		if len(result) == 0:
			return False
		elif len(result) == 1:
			return True
		else:
			raise cache_errors.CacheCorruption(cpv, "key is not unique")

	def iterkeys(self):
		"""generator for walking the dir struct"""
		cursor = self._db_cursor
		cursor.execute("SELECT %s FROM %s" % \
			(self._db_table["packages"]["package_key"],
			self._db_table["packages"]["table_name"]))
		result = cursor.fetchall()
		key_list = [x[0] for x in result]
		del result
		while key_list:
			yield key_list.pop()
