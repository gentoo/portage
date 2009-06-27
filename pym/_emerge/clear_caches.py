# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import gc

# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
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
