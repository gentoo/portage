# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import collections
import re

import portage
from portage.cache import fs_template
from portage.cache import cache_errors
from portage import os
from portage import _unicode_decode
from portage.util import writemsg
from portage.localization import _


class database(fs_template.FsBased):

	validation_chf = 'md5'
	chf_types = ('md5', 'mtime')

	autocommits = False
	synchronous = False
	# cache_bytes is used together with page_size (set at sqlite build time)
	# to calculate the number of pages requested, according to the following
	# equation: cache_bytes = page_bytes * page_count
	cache_bytes = 1024 * 1024 * 10

	_connection_info_entry = collections.namedtuple('_connection_info_entry',
		('connection', 'cursor', 'pid'))

	def __init__(self, *args, **config):
		super(database, self).__init__(*args, **config)
		self._import_sqlite()
		self._allowed_keys = ["_eclasses_"]
		self._allowed_keys.extend(self._known_keys)
		self._allowed_keys.extend('_%s_' % k for k in self.chf_types)
		self._allowed_keys_set = frozenset(self._allowed_keys)
		self._allowed_keys = sorted(self._allowed_keys_set)

		self.location = os.path.join(self.location,
			self.label.lstrip(os.path.sep).rstrip(os.path.sep))

		if not self.readonly and not os.path.exists(self.location):
			self._ensure_dirs()

		config.setdefault("autocommit", self.autocommits)
		config.setdefault("cache_bytes", self.cache_bytes)
		config.setdefault("synchronous", self.synchronous)
		# Set longer timeout for throwing a "database is locked" exception.
		# Default timeout in sqlite3 module is 5.0 seconds.
		config.setdefault("timeout", 15)
		self._config = config
		self._db_connection_info = None

	def _import_sqlite(self):
		# sqlite3 is optional with >=python-2.5
		try:
			import sqlite3 as db_module
		except ImportError as e:
			raise cache_errors.InitializationError(self.__class__, e)

		self._db_module = db_module
		self._db_error = db_module.Error

	def _db_escape_string(self, s):
		"""meta escaping, returns quoted string for use in sql statements"""
		if not isinstance(s, str):
			# Avoid potential UnicodeEncodeError in python-2.x by
			# only calling str() when it's absolutely necessary.
			s = str(s)
		return "'%s'" % s.replace("'", "''")

	@property
	def _db_cursor(self):
		if self._db_connection_info is None or self._db_connection_info.pid != portage.getpid():
			self._db_init_connection()
		return self._db_connection_info.cursor

	@property
	def _db_connection(self):
		if self._db_connection_info is None or self._db_connection_info.pid != portage.getpid():
			self._db_init_connection()
		return self._db_connection_info.connection

	def _db_init_connection(self):
		config = self._config
		self._dbpath = self.location + ".sqlite"
		#if os.path.exists(self._dbpath):
		#	os.unlink(self._dbpath)
		connection_kwargs = {}
		connection_kwargs["timeout"] = config["timeout"]
		try:
			if not self.readonly:
				self._ensure_dirs()
			connection = self._db_module.connect(
				database=_unicode_decode(self._dbpath), **connection_kwargs)
			cursor = connection.cursor()
			self._db_connection_info = self._connection_info_entry(connection, cursor, portage.getpid())
			self._db_cursor.execute("PRAGMA encoding = %s" % self._db_escape_string("UTF-8"))
			if not self.readonly and not self._ensure_access(self._dbpath):
				raise cache_errors.InitializationError(self.__class__, "can't ensure perms on %s" % self._dbpath)
			self._db_init_cache_size(config["cache_bytes"])
			self._db_init_synchronous(config["synchronous"])
			self._db_init_structures()
		except self._db_error as e:
			raise cache_errors.InitializationError(self.__class__, e)

	def _db_init_structures(self):
		self._db_table = {}
		self._db_table["packages"] = {}
		mytable = "portage_packages"
		self._db_table["packages"]["table_name"] = mytable
		self._db_table["packages"]["package_id"] = "internal_db_package_id"
		self._db_table["packages"]["package_key"] = "portage_package_key"
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

		cursor = self._db_cursor
		for k, v in self._db_table.items():
			if self._db_table_exists(v["table_name"]):
				create_statement = self._db_table_get_create(v["table_name"])
				table_ok, missing_keys = self._db_validate_create_statement(create_statement)
				if table_ok:
					if missing_keys:
						for k in sorted(missing_keys):
							cursor.execute("ALTER TABLE %s ADD COLUMN %s TEXT" %
								(self._db_table["packages"]["table_name"], k))
				else:
					writemsg(_("sqlite: dropping old table: %s\n") % v["table_name"])
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

	def _db_validate_create_statement(self, statement):
		missing_keys = None
		if statement == self._db_table["packages"]["create"]:
			return True, missing_keys

		m = re.match(r'^\s*CREATE\s*TABLE\s*%s\s*\(\s*%s\s*INTEGER\s*PRIMARY\s*KEY\s*AUTOINCREMENT\s*,(.*)\)\s*$' %
			(self._db_table["packages"]["table_name"],
			self._db_table["packages"]["package_id"]),
			statement)
		if m is None:
			return False, missing_keys

		unique_constraints = set([self._db_table["packages"]["package_key"]])
		missing_keys = set(self._allowed_keys)
		unique_re = re.compile(r'^\s*UNIQUE\s*\(\s*(\w*)\s*\)\s*$')
		column_re = re.compile(r'^\s*(\w*)\s*TEXT\s*$')
		for x in m.group(1).split(","):
			m = column_re.match(x)
			if m is not None:
				missing_keys.discard(m.group(1))
				continue
			m = unique_re.match(x)
			if m is not None:
				unique_constraints.discard(m.group(1))
				continue

		if unique_constraints:
			return False, missing_keys

		return True, missing_keys

	def _db_init_cache_size(self, cache_bytes):
		cursor = self._db_cursor
		cursor.execute("PRAGMA page_size")
		page_size=int(cursor.fetchone()[0])
		# number of pages, sqlite default is 2000
		cache_size = cache_bytes // page_size
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

	def _getitem(self, cpv):
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
		result = result[0]
		d = {}
		allowed_keys_set = self._allowed_keys_set
		for column_index, column_info in enumerate(cursor.description):
			k = column_info[0]
			if k in allowed_keys_set:
				v = result[column_index]
				if v is None:
					# This happens after a new empty column has been added.
					v = ""
				d[k] = v

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
		except self._db_error as e:
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

	def __contains__(self, cpv):
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
		if len(result) == 1:
			return True
		raise cache_errors.CacheCorruption(cpv, "key is not unique")

	def __iter__(self):
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
