# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: /var/cvsroot/gentoo-src/portage/pym/Attic/portage_db_flat.py,v 1.13.2.6 2005/04/19 07:14:17 ferringb Exp $
cvs_id_string="$Id: portage_db_flat.py,v 1.13.2.6 2005/04/19 07:14:17 ferringb Exp $"[5:-2]

import os, portage_db_flat_hash, portage_db_flat

class database(portage_db_flat_hash.database):
	
	def get_values(self, key):
		if not key:
			raise KeyError("key is not valid")
		
		try:
			myf = open(self.fullpath + key, "r")
		except OSError:
			raise KeyError("key is not valid")
		mtime = os.fstat(myf.fileno()).st_mtime
		data = myf.read().splitlines()
		
		# easy attempt first.
		if len(data) != portage_db_flat.magic_line_count:
			d = dict(map(lambda x: x.split("=",1), data))
			d["_mtime_"] = mtime
			return portage_db_flat_hash.database.get_values(self, key, d)
		# this one's interesting.
		d = {}

		for line in data:
			# yes, meant to iterate over a string.
			hashed = False
			for idx, c in enumerate(line):
				if not c.isalpha():
					if c == "=" and idx > 0:
						hashed = True
						d[line[:idx]] = line[idx + 1:]
					elif c == "_" or c.isdigit():
						continue
					break
				elif not c.isupper():
					break

			if not hashed:
				# non hashed.
				data.append(mtime)
				return portage_db_flat.database.get_values(self, key, data=data)

		d["_mtime_"] = mtime
		return portage_db_flat_hash.database.get_values(self, key, data=d)
