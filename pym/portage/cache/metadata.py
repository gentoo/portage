# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id$

import os, stat, types
from cache import flat_hash
import eclass_cache 
from cache.template import reconstruct_eclasses
from cache.mappings import ProtectedDict

# this is the old cache format, flat_list.  count maintained here.
magic_line_count = 22

# store the current key order *here*.
class database(flat_hash.database):
	complete_eclass_entries = False
	auxdbkey_order=('DEPEND', 'RDEPEND', 'SLOT', 'SRC_URI',
		'RESTRICT',  'HOMEPAGE',  'LICENSE', 'DESCRIPTION',
		'KEYWORDS',  'INHERITED', 'IUSE', 'CDEPEND',
		'PDEPEND',   'PROVIDE', 'EAPI')

	autocommits = True

	def __init__(self, location, *args, **config):
		loc = location
		super(database, self).__init__(location, *args, **config)
		self.location = os.path.join(loc, "metadata","cache")
		self.ec = eclass_cache.cache(loc)

	def __getitem__(self, cpv):
		return flat_hash.database.__getitem__(self, cpv)


	def _parse_data(self, data, cpv):
		# easy attempt first.
		data = list(data)
		if len(data) != magic_line_count:
			d = flat_hash.database._parse_data(self, data, cpv)
		else:
			# this one's interesting.
			d = {}

			for line in data:
				# yes, meant to iterate over a string.
				hashed = False
				# poor mans enumerate.  replace when python 2.3 is required
				for idx, c in zip(range(len(line)), line):
					if not c.isalpha():
						if c == "=" and idx > 0:
							hashed = True
							d[line[:idx]] = line[idx + 1:].rstrip("\n")
						elif c == "_" or c.isdigit():
							continue
						break

				if not hashed:
					# non hashed.
					d.clear()
					# poor mans enumerate.  replace when python 2.3 is required
					for idx, key in zip(range(len(self.auxdbkey_order)), self.auxdbkey_order):
						d[key] = data[idx].strip()
					break

		if "_eclasses_" not in d:
			if "INHERITED" in d:
				d["_eclasses_"] = self.ec.get_eclass_data(d["INHERITED"].split(), from_master_only=True)
				del d["INHERITED"]
		elif isinstance(d["_eclasses_"], basestring):
			# We skip this if flat_hash.database._parse_data() was called above
			# because it calls reconstruct_eclasses() internally.
			d["_eclasses_"] = reconstruct_eclasses(None, d["_eclasses_"])

		return d


		
	def _setitem(self, cpv, values):
		values = ProtectedDict(values)
		
		# hack.  proper solution is to make this a __setitem__ override, since template.__setitem__ 
		# serializes _eclasses_, then we reconstruct it.
		if "_eclasses_" in values:
			values["INHERITED"] = ' '.join(reconstruct_eclasses(cpv, values["_eclasses_"]).keys())
			del values["_eclasses_"]

		flat_hash.database._setitem(self, cpv, values)
