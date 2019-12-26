# Copyright 2005-2021 Gentoo Authors
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2

import errno
import re
import stat
from operator import attrgetter

import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.cache import cache_errors, flat_hash
import portage.eclass_cache
from portage.cache.template import reconstruct_eclasses
from portage.cache.mappings import ProtectedDict


# this is the old cache format, flat_list.  count maintained here.
magic_line_count = 22

# store the current key order *here*.
class database(flat_hash.database):
	complete_eclass_entries = False
	auxdbkey_order=('DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
		'RESTRICT',  'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
		'KEYWORDS',  'IDEPEND',   'INHERITED', 'IUSE', 'REQUIRED_USE',
		'PDEPEND',   'BDEPEND',   'EAPI', 'PROPERTIES',
		'DEFINED_PHASES')

	autocommits = True
	serialize_eclasses = False

	_hashed_re = re.compile('^(\\w+)=([^\n]*)')

	def __init__(self, location, *args, **config):
		loc = location
		super(database, self).__init__(location, *args, **config)
		self.location = os.path.join(loc, "metadata","cache")
		self.ec = None
		self.raise_stat_collision = False

	def _parse_data(self, data, cpv):
		_hashed_re_match = self._hashed_re.match
		d = {}

		for line in data:
			hashed = False
			hashed_match = _hashed_re_match(line)
			if hashed_match is None:
				d.clear()
				try:
					for i, key in enumerate(self.auxdbkey_order):
						d[key] = data[i]
				except IndexError:
					pass
				break
			else:
				d[hashed_match.group(1)] = hashed_match.group(2)

		if "_eclasses_" not in d:
			if "INHERITED" in d:
				if self.ec is None:
					self.ec = portage.eclass_cache.cache(self.location[:-15])
				getter = attrgetter(self.validation_chf)
				try:
					ec_data = self.ec.get_eclass_data(d["INHERITED"].split())
					d["_eclasses_"] = dict((k, (v.eclass_dir, getter(v)))
						for k,v in ec_data.items())
				except KeyError as e:
					# INHERITED contains a non-existent eclass.
					raise cache_errors.CacheCorruption(cpv, e)
			else:
				d["_eclasses_"] = {}
		elif isinstance(d["_eclasses_"], str):
			# We skip this if flat_hash.database._parse_data() was called above
			# because it calls reconstruct_eclasses() internally.
			d["_eclasses_"] = reconstruct_eclasses(None, d["_eclasses_"])

		return d

	def _setitem(self, cpv, values):
		if "_eclasses_" in values:
			values = ProtectedDict(values)
			values["INHERITED"] = ' '.join(sorted(values["_eclasses_"]))

		new_content = []
		for k in self.auxdbkey_order:
			new_content.append(values.get(k, ''))
			new_content.append('\n')
		for i in range(magic_line_count - len(self.auxdbkey_order)):
			new_content.append('\n')
		new_content = ''.join(new_content)
		new_content = _unicode_encode(new_content,
			_encodings['repo.content'], errors='backslashreplace')

		new_fp = os.path.join(self.location, cpv)
		try:
			f = open(_unicode_encode(new_fp,
				encoding=_encodings['fs'], errors='strict'), 'rb')
		except EnvironmentError:
			pass
		else:
			try:
				try:
					existing_st = os.fstat(f.fileno())
					existing_content = f.read()
				finally:
					f.close()
			except EnvironmentError:
				pass
			else:
				existing_mtime = existing_st[stat.ST_MTIME]
				if values['_mtime_'] == existing_mtime and \
					existing_content == new_content:
					return

				if self.raise_stat_collision and \
					values['_mtime_'] == existing_mtime and \
					len(new_content) == existing_st.st_size:
					raise cache_errors.StatCollision(cpv, new_fp,
						existing_mtime, existing_st.st_size)

		s = cpv.rfind("/")
		fp = os.path.join(self.location,cpv[:s],
			".update.%i.%s" % (portage.getpid(), cpv[s+1:]))
		try:
			myf = open(_unicode_encode(fp,
				encoding=_encodings['fs'], errors='strict'), 'wb')
		except EnvironmentError as e:
			if errno.ENOENT == e.errno:
				try:
					self._ensure_dirs(cpv)
					myf = open(_unicode_encode(fp,
						encoding=_encodings['fs'], errors='strict'), 'wb')
				except EnvironmentError as e:
					raise cache_errors.CacheCorruption(cpv, e)
			else:
				raise cache_errors.CacheCorruption(cpv, e)

		try:
			myf.write(new_content)
		finally:
			myf.close()
		self._ensure_access(fp, mtime=values["_mtime_"])

		try:
			os.rename(fp, new_fp)
		except EnvironmentError as e:
			try:
				os.unlink(fp)
			except EnvironmentError:
				pass
			raise cache_errors.CacheCorruption(cpv, e)
