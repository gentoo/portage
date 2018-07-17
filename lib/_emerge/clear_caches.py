# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import gc

def clear_caches(trees):
	for d in trees.values():
		d["porttree"].dbapi.melt()
		d["porttree"].dbapi._aux_cache.clear()
		d["bintree"].dbapi._clear_cache()
		if d["vartree"].dbapi._linkmap is None:
			# preserve-libs is entirely disabled
			pass
		else:
			d["vartree"].dbapi._linkmap._clear_cache()
	gc.collect()
