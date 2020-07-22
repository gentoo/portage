# Copyright 2013-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
import stat

from portage import os
from .DeletionTask import DeletionTask

class DeletionIterator:

	def __init__(self, config):
		self._config = config

	def __iter__(self):
		distdir = self._config.options.distfiles
		file_owners = self._config.file_owners
		whitelist = self._config.whitelist
		distfiles_local = self._config.options.distfiles_local
		deletion_db = self._config.deletion_db
		deletion_delay = self._config.options.deletion_delay
		start_time = self._config.start_time
		distfiles_set = set()
		for layout in self._config.layouts:
			distfiles_set.update(layout.get_filenames(distdir))
		for filename in distfiles_set:
			# require at least one successful stat()
			exceptions = []
			for layout in reversed(self._config.layouts):
				path = os.path.join(distdir, layout.get_path(filename))
				try:
					st = os.stat(path)
				except OSError as e:
					# is it a dangling symlink?
					try:
						if os.path.islink(path):
							os.unlink(path)
					except OSError as e:
						exceptions.append(e)
				else:
					if stat.S_ISREG(st.st_mode):
						break
			else:
				if exceptions:
					logging.error("stat failed on '%s' in distfiles: %s\n" %
						(filename, '; '.join(str(x) for x in exceptions)))
				continue

			if filename in file_owners:
				if deletion_db is not None:
					try:
						del deletion_db[filename]
					except KeyError:
						pass
			elif whitelist is not None and filename in whitelist:
				if deletion_db is not None:
					try:
						del deletion_db[filename]
					except KeyError:
						pass
			elif distfiles_local is not None and \
				os.path.exists(os.path.join(distfiles_local, filename)):
				if deletion_db is not None:
					try:
						del deletion_db[filename]
					except KeyError:
						pass
			else:
				self._config.scheduled_deletion_count += 1

				if deletion_db is None or deletion_delay is None:

					yield DeletionTask(background=True,
						distfile=filename,
						distfile_path=path,
						config=self._config)

				else:
					deletion_entry = deletion_db.get(filename)

					if deletion_entry is None:
						logging.debug("add '%s' to deletion db" % filename)
						deletion_db[filename] = start_time

					elif deletion_entry + deletion_delay <= start_time:

						yield DeletionTask(background=True,
							distfile=filename,
							distfile_path=path,
							config=self._config)

		if deletion_db is not None:
			for filename in list(deletion_db):
				if filename not in distfiles_set:
					try:
						del deletion_db[filename]
					except KeyError:
						pass
					else:
						logging.debug("drop '%s' from deletion db" %
							filename)
