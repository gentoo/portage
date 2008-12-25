# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

import os, re, stat, types
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
		'KEYWORDS',  'INHERITED', 'IUSE', 'CDEPEND',
		'PDEPEND',   'PROVIDE', 'EAPI', 'PROPERTIES', 'DEFINED_PHASES')

	autocommits = True

	_hashed_re = re.compile('^(\\w+)=([^\n]*)')

	def __init__(self, location, *args, **config):
		loc = location
		super(database, self).__init__(location, *args, **config)
		self.location = os.path.join(loc, "metadata","cache")
		self.ec = portage.eclass_cache.cache(loc)

	def __getitem__(self, cpv):
		return flat_hash.database.__getitem__(self, cpv)


	def _parse_data(self, data, cpv):
		_hashed_re_match = self._hashed_re.match
		data = list(data)
		d = {}

		for line in data:
			hashed = False
			hashed_match = _hashed_re_match(line)
			if hashed_match is None:
				d.clear()
				try:
					for i, key in enumerate(self.auxdbkey_order):
						d[key] = data[i].rstrip("\n")
				except IndexError:
					pass
				break
			else:
				d[hashed_match.group(1)] = hashed_match.group(2)

		if "_eclasses_" not in d:
			if "INHERITED" in d:
				try:
					d["_eclasses_"] = self.ec.get_eclass_data(
						d["INHERITED"].split(), from_master_only=True)
				except KeyError, e:
					# INHERITED contains a non-existent eclass.
					raise cache_errors.CacheCorruption(cpv, e)
				del d["INHERITED"]
			else:
				d["_eclasses_"] = {}
		elif isinstance(d["_eclasses_"], basestring):
			# We skip this if flat_hash.database._parse_data() was called above
			# because it calls reconstruct_eclasses() internally.
			d["_eclasses_"] = reconstruct_eclasses(None, d["_eclasses_"])

		for x in self._known_keys:
			d.setdefault(x, '')

		return d


		
	def _setitem(self, cpv, values):
		flat_hash.database._setitem(self, cpv, values)
