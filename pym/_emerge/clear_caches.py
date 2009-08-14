# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import gc
import portage

def clear_caches(trees):
	for d in trees.itervalues():
		d["porttree"].dbapi.melt()
		d["porttree"].dbapi._aux_cache.clear()
		d["bintree"].dbapi._aux_cache.clear()
		d["bintree"].dbapi._clear_cache()
		d["vartree"].dbapi.linkmap._clear_cache()
	portage.dircache.clear()
	gc.collect()
