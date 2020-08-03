# Copyright 2013-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import copy
import io
import logging
import shelve
import time

from portage import os
from portage.package.ebuild.fetch import MirrorLayoutConfig
from portage.util import grabdict, grablines

class Config:
	def __init__(self, options, portdb, event_loop):
		self.options = options
		self.portdb = portdb
		self.event_loop = event_loop
		self.added_byte_count = 0
		self.added_file_count = 0
		self.scheduled_deletion_count = 0
		self.delete_count = 0
		self.file_owners = {}
		self.file_failures = {}
		self.start_time = time.time()
		self._open_files = []

		self.log_success = self._open_log('success', options.success_log, 'a')
		self.log_failure = self._open_log('failure', options.failure_log, 'a')

		self.distfiles = None
		if options.distfiles is not None:
			self.distfiles = options.distfiles

		self.mirrors = copy.copy(portdb.settings.thirdpartymirrors())

		if options.mirror_overrides is not None:
			self.mirrors.update(grabdict(options.mirror_overrides))

		if options.mirror_skip is not None:
			for x in options.mirror_skip.split(","):
				self.mirrors[x] = []

		self.whitelist = None
		if options.whitelist_from is not None:
			self.whitelist = set()
			for filename in options.whitelist_from:
				for line in grablines(filename):
					line = line.strip()
					if line and not line.startswith("#"):
						self.whitelist.add(line)

		self.restrict_mirror_exemptions = None
		if options.restrict_mirror_exemptions is not None:
			self.restrict_mirror_exemptions = frozenset(
				options.restrict_mirror_exemptions.split(","))

		self.recycle_db = None
		if options.recycle_db is not None:
			self.recycle_db = self._open_shelve(
				options.recycle_db, 'recycle')

		self.distfiles_db = None
		if options.distfiles_db is not None:
			self.distfiles_db = self._open_shelve(
				options.distfiles_db, 'distfiles')

		self.deletion_db = None
		if options.deletion_db is not None:
			self.deletion_db = self._open_shelve(
				options.deletion_db, 'deletion')

		self.layout_conf = MirrorLayoutConfig()
		if options.layout_conf is None:
			options.layout_conf = os.path.join(self.distfiles,
					'layout.conf')
		self.layout_conf.read_from_file(options.layout_conf)
		self.layouts = self.layout_conf.get_all_layouts()

	def _open_log(self, log_desc, log_path, mode):

		if log_path is None or self.options.dry_run:
			log_func = logging.info
			line_format = "%s: %%s" % log_desc
			add_newline = False
			if log_path is not None:
				logging.warning("dry-run: %s log "
					"redirected to logging.info" % log_desc)
		else:
			self._open_files.append(io.open(log_path, mode=mode,
				encoding='utf_8'))
			line_format = "%s\n"
			log_func = self._open_files[-1].write

		return self._LogFormatter(line_format, log_func)

	class _LogFormatter:

		__slots__ = ('_line_format', '_log_func')

		def __init__(self, line_format, log_func):
			self._line_format = line_format
			self._log_func = log_func

		def __call__(self, msg):
			self._log_func(self._line_format % (msg,))

	def _open_shelve(self, db_file, db_desc):
		if self.options.dry_run:
			open_flag = "r"
		else:
			open_flag = "c"

		if self.options.dry_run and not os.path.exists(db_file):
			db = {}
		else:
			try:
				db = shelve.open(db_file, flag=open_flag)
			except ImportError as e:
				# ImportError has different attributes for python2 vs. python3
				if (getattr(e, 'name', None) == 'bsddb' or
					getattr(e, 'message', None) == 'No module named bsddb'):
					from bsddb3 import dbshelve
					db = dbshelve.open(db_file, flags=open_flag)

		if self.options.dry_run:
			logging.warning("dry-run: %s db opened in readonly mode" % db_desc)
			if not isinstance(db, dict):
				volatile_db = dict((k, db[k]) for k in db)
				db.close()
				db = volatile_db
		else:
			self._open_files.append(db)

		return db

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		while self._open_files:
			self._open_files.pop().close()
