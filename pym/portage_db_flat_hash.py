# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: /var/cvsroot/gentoo-src/portage/pym/Attic/portage_db_flat.py,v 1.13.2.6 2005/04/19 07:14:17 ferringb Exp $
cvs_id_string="$Id: portage_db_flat.py,v 1.13.2.6 2005/04/19 07:14:17 ferringb Exp $"[5:-2]

import portage_db_flat, os

class database(portage_db_flat.database):
	
	def get_values(self, key, data=None):
		""" do not specify data unless you know what it does"""
		if not key:
			raise KeyError("key is not valid")
		
		if data == None:
			try:
				myf = open(self.fullpath + key, "r")
			except OSError:
				raise KeyError("failed pulling key")

			data = dict(map(lambda x: x.split("=",1), myf.read().splitlines()))
			data["_mtime_"] = os.fstat(myf.fileno()).st_mtime
			myf.close()

		mydict = {}
		for x in self.dbkeys:
			mydict[x] = data.get(x, "")
		mydict["_mtime_"] = long(data["_mtime_"])
		return mydict
		
	def set_values(self, key, values):
		l = []
		for x in values.keys():
			if values[x] and x != "_mtime_":
				l.append("%s=%s\n" % (x, values[x]))
		l.append(values["_mtime_"])
		portage_db_flat.database.set_values(self, key, l, raw=True)
		
