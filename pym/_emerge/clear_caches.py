# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import gc
import portage
from portage.util.listdir import dircache

def clear_caches(trees):
	for d in trees.values():
		d["porttree"].dbapi.melt()
		d["porttree"].dbapi._aux_cache.clear()
		d["bintree"].dbapi._aux_cache.clear()
		d["bintree"].dbapi._clear_cache()
		d["vartree"].dbapi.linkmap._clear_cache()
	dircache.clear()
	gc.collect()
