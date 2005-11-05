# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: sqlite.py 1911 2005-08-25 03:44:21Z ferringb $

sqlite_module =__import__("sqlite")
import os
import sql_template, fs_template
import cache_errors

class database(fs_template.FsBased, sql_template.SQLDatabase):

	SCHEMA_DELETE_NAME	= "delete_package_values"
	SCHEMA_DELETE_TRIGGER	= """CREATE TRIGGER %s AFTER DELETE on %s
	begin
	DELETE FROM %s WHERE pkgid=old.pkgid;
	end;""" % (SCHEMA_DELETE_NAME, sql_template.SQLDatabase.SCHEMA_PACKAGE_NAME, 
		sql_template.SQLDatabase.SCHEMA_VALUES_NAME)

	_BaseError = sqlite_module.Error
	_dbClass = sqlite_module
	_supports_replace = True

	def _dbconnect(self, config):
		self._dbpath = os.path.join(self.location, fs_template.gen_label(self.location, self.label)+".sqldb")
		try:
			self.db = sqlite_module.connect(self._dbpath, mode=self._perms, autocommit=False)
			if not self._ensure_access(self._dbpath):
				raise cache_errors.InitializationError(self.__class__, "can't ensure perms on %s" % self._dbpath)
			self.con = self.db.cursor()
		except self._BaseError, e:
			raise cache_errors.InitializationError(self.__class__, e)

		
	def _initdb_con(self, config):
		sql_template.SQLDatabase._initdb_con(self, config)
		try:
			self.con.execute("SELECT name FROM sqlite_master WHERE type=\"trigger\" AND name=%s" % \
				self._sfilter(self.SCHEMA_DELETE_NAME))
			if self.con.rowcount == 0:
				self.con.execute(self.SCHEMA_DELETE_TRIGGER);
				self.db.commit()
		except self._BaseError, e:
			raise cache_errors.InitializationError(self.__class__, e)

	def _table_exists(self, tbl):
		"""return true/false dependant on a tbl existing"""
		try:	self.con.execute("SELECT name FROM sqlite_master WHERE type=\"table\" AND name=%s" % 
			self._sfilter(tbl))
		except self._BaseError, e:
			# XXX crappy.
			return False
		return len(self.con.fetchall()) == 1

	# we can do it minus a query via rowid.
	def _insert_cpv(self, cpv):
		cpv = self._sfilter(cpv)
		try:	self.con.execute(self.SCHEMA_INSERT_CPV_INTO_PACKAGE.replace("INSERT","REPLACE",1) % \
			(self.label, cpv))
		except self._BaseError, e:
			raise cache_errors.CacheCorruption(cpv, "tried to insert a cpv, but failed: %s" % str(e))

		# sums the delete also
		if self.con.rowcount <= 0 or self.con.rowcount > 2:
			raise cache_errors.CacheCorruption(cpv, "tried to insert a cpv, but failed- %i rows modified" % self.rowcount)
		return self.con.lastrowid

