# Copyright 2007-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import logging

import portage
from portage.output import colorize

def display_preserved_libs(vardb):

	MAX_DISPLAY = 3

	plibdata = vardb._plib_registry.getPreservedLibs()
	linkmap = vardb._linkmap
	consumer_map = {}
	owners = {}

	try:
		linkmap.rebuild()
	except portage.exception.CommandNotFound as e:
		portage.util.writemsg_level("!!! Command Not Found: %s\n" % (e,),
			level=logging.ERROR, noiselevel=-1)
	else:
		search_for_owners = set()
		for cpv in plibdata:
			internal_plib_keys = set(linkmap._obj_key(f) \
				for f in plibdata[cpv])
			for f in plibdata[cpv]:
				if f in consumer_map:
					continue
				consumers = []
				for c in linkmap.findConsumers(f):
					# Filter out any consumers that are also preserved libs
					# belonging to the same package as the provider.
					if linkmap._obj_key(c) not in internal_plib_keys:
						consumers.append(c)
				consumers.sort()
				consumer_map[f] = consumers
				search_for_owners.update(consumers[:MAX_DISPLAY+1])

		owners = {}
		for f in search_for_owners:
			owner_set = set()
			for owner in linkmap.getOwners(f):
				owner_dblink = vardb._dblink(owner)
				if owner_dblink.exists():
					owner_set.add(owner_dblink)
			if owner_set:
				owners[f] = owner_set

	for cpv in plibdata:
		print(colorize("WARN", ">>>") + " package: %s" % cpv)
		samefile_map = {}
		for f in plibdata[cpv]:
			obj_key = linkmap._obj_key(f)
			alt_paths = samefile_map.get(obj_key)
			if alt_paths is None:
				alt_paths = set()
				samefile_map[obj_key] = alt_paths
			alt_paths.add(f)

		for alt_paths in samefile_map.values():
			alt_paths = sorted(alt_paths)
			for p in alt_paths:
				print(colorize("WARN", " * ") + " - %s" % (p,))
			f = alt_paths[0]
			consumers = consumer_map.get(f, [])
			for c in consumers[:MAX_DISPLAY]:
				print(colorize("WARN", " * ") + "     used by %s (%s)" % \
					(c, ", ".join(x.mycpv for x in owners.get(c, []))))
			if len(consumers) == MAX_DISPLAY + 1:
				print(colorize("WARN", " * ") + "     used by %s (%s)" % \
					(consumers[MAX_DISPLAY], ", ".join(x.mycpv \
					for x in owners.get(consumers[MAX_DISPLAY], []))))
			elif len(consumers) > MAX_DISPLAY:
				print(colorize("WARN", " * ") + "     used by %d other files" %
					(len(consumers) - MAX_DISPLAY))
