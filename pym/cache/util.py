# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id: util.py 1911 2005-08-25 03:44:21Z ferringb $

import cache_errors

def mirror_cache(valid_nodes_iterable, src_cache, trg_cache, eclass_cache=None, verbose_instance=None):

	if not src_cache.complete_eclass_entries and not eclass_cache:
		raise Exception("eclass_cache required for cache's of class %s!" % src_cache.__class__)

	if verbose_instance == None:
		noise=quiet_mirroring()
	else:
		noise=verbose_instance

	dead_nodes = {}
	dead_nodes = dict.fromkeys(trg_cache.keys())
	count=0

	if not trg_cache.autocommits:
		trg_cache.sync(100)

	for x in valid_nodes_iterable:
#		print "processing x=",x
		count+=1
		if dead_nodes.has_key(x):
			del dead_nodes[x]
		try:	entry = src_cache[x]
		except KeyError, e:
			noise.missing_entry(x)
			del e
			continue
		write_it = True
		try:
			trg = trg_cache[x]
			if long(trg["_mtime_"]) == long(entry["_mtime_"]) and eclass_cache.is_eclass_data_valid(trg["_eclasses_"]):
				write_it = False
		except (cache_errors.CacheError, KeyError):
			pass

		if write_it:
			if entry.get("INHERITED",""):
				if src_cache.complete_eclass_entries:
					if not "_eclasses_" in entry:
						noise.corruption(x,"missing _eclasses_ field")
						continue
					if not eclass_cache.is_eclass_data_valid(entry["_eclasses_"]):
						noise.eclass_stale(x)
						continue
				else:
					entry["_eclasses_"] = eclass_cache.get_eclass_data(entry["INHERITED"].split(), \
						from_master_only=True)
					if not entry["_eclasses_"]:
						noise.eclass_stale(x)
						continue

			# by this time, if it reaches here, the eclass has been validated, and the entry has 
			# been updated/translated (if needs be, for metadata/cache mainly)
			try:	trg_cache[x] = entry
			except cache_errors.CacheError, ce:
				noise.exception(x, ce)
				del ce
				continue
		if count >= noise.call_update_min:
			noise.update(x)
			count = 0

	if not trg_cache.autocommits:
		trg_cache.commit()

	# ok.  by this time, the trg_cache is up to date, and we have a dict
	# with a crapload of cpv's.  we now walk the target db, removing stuff if it's in the list.
	for key in dead_nodes:
		try:	del trg_cache[key]
		except cache_errors.CacheError, ce:
			noise.exception(ce)
			del ce
	dead_nodes.clear()
	noise.finish()


class quiet_mirroring(object):
	# call_update_every is used by mirror_cache to determine how often to call in.
	# quiet defaults to 2^24 -1.  Don't call update, 'cept once every 16 million or so :)
	call_update_min = 0xffffff
	def update(self,key,*arg):		pass
	def exception(self,key,*arg):	pass
	def eclass_stale(self,*arg):	pass
	def missing_entry(self, key):	pass
	def misc(self,key,*arg):		pass
	def corruption(self, key, s):	pass
	def finish(self, *arg):			pass
	
class non_quiet_mirroring(quiet_mirroring):
	call_update_min=1
	def update(self,key,*arg):	print "processed",key
	def exception(self, key, *arg):	print "exec",key,arg
	def missing(self,key):		print "key %s is missing", key
	def corruption(self,key,*arg):	print "corrupt %s:" % key,arg
	def eclass_stale(self,key,*arg):print "stale %s:"%key,arg

