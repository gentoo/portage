# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2

from __future__ import print_function

__all__ = ["mirror_cache", "non_quiet_mirroring", "quiet_mirroring"]

from itertools import chain
from portage.cache import cache_errors
from portage.localization import _

def mirror_cache(valid_nodes_iterable, src_cache, trg_cache, eclass_cache=None, verbose_instance=None):

	from portage import eapi_is_supported, \
		_validate_cache_for_unsupported_eapis
	if not src_cache.complete_eclass_entries and not eclass_cache:
		raise Exception("eclass_cache required for cache's of class %s!" % src_cache.__class__)

	if verbose_instance == None:
		noise=quiet_mirroring()
	else:
		noise=verbose_instance

	dead_nodes = set(trg_cache)
	count=0

	if not trg_cache.autocommits:
		trg_cache.sync(100)

	for x in valid_nodes_iterable:
#		print "processing x=",x
		count+=1
		dead_nodes.discard(x)
		try:
			entry = src_cache[x]
		except KeyError as e:
			noise.missing_entry(x)
			del e
			continue
		except cache_errors.CacheError as ce:
			noise.exception(x, ce)
			del ce
			continue

		eapi = entry.get('EAPI')
		if not eapi:
			eapi = '0'
		eapi = eapi.lstrip('-')
		eapi_supported = eapi_is_supported(eapi)
		if not eapi_supported:
			if not _validate_cache_for_unsupported_eapis:
				noise.misc(x, _("unable to validate cache for EAPI='%s'") % eapi)
				continue

		write_it = True
		trg = None
		try:
			trg = trg_cache[x]
		except (KeyError, cache_errors.CacheError):
			pass
		else:
			if trg['_mtime_'] == entry['_mtime_'] and \
				eclass_cache.is_eclass_data_valid(trg['_eclasses_']) and \
				set(trg['_eclasses_']) == set(entry['_eclasses_']):
				write_it = False

		for d in (entry, trg):
			if d is not None and d.get('EAPI') in ('', '0'):
				del d['EAPI']

		if trg and not write_it:
			""" We don't want to skip the write unless we're really sure that
			the existing cache is identical, so don't trust _mtime_ and
			_eclasses_ alone."""
			for k in set(chain(entry, trg)).difference(
				("_mtime_", "_eclasses_")):
				if trg.get(k, "") != entry.get(k, ""):
					write_it = True
					break

		if write_it:
			try:
				inherited = entry.get("INHERITED", "")
				eclasses = entry.get("_eclasses_")
			except cache_errors.CacheError as ce:
				noise.exception(x, ce)
				del ce
				continue

			if eclasses is not None:
				if not eclass_cache.is_eclass_data_valid(entry["_eclasses_"]):
					noise.eclass_stale(x)
					continue
				inherited = eclasses
			else:
				inherited = inherited.split()

			if inherited:
				if src_cache.complete_eclass_entries and eclasses is None:
					noise.corruption(x, "missing _eclasses_ field")
					continue

				# Even if _eclasses_ already exists, replace it with data from
				# eclass_cache, in order to insert local eclass paths.
				try:
					eclasses = eclass_cache.get_eclass_data(inherited)
				except KeyError:
					# INHERITED contains a non-existent eclass.
					noise.eclass_stale(x)
					continue

				if eclasses is None:
					noise.eclass_stale(x)
					continue
				entry["_eclasses_"] = eclasses

			if not eapi_supported:
				for k in set(entry).difference(("_mtime_", "_eclasses_")):
					entry[k] = ""
				entry["EAPI"] = "-" + eapi

			# by this time, if it reaches here, the eclass has been validated, and the entry has 
			# been updated/translated (if needs be, for metadata/cache mainly)
			try:
				trg_cache[x] = entry
			except cache_errors.CacheError as ce:
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
		try:
			del trg_cache[key]
		except KeyError:
			pass
		except cache_errors.CacheError as ce:
			noise.exception(ce)
			del ce
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
	def update(self,key,*arg):	print("processed",key)
	def exception(self, key, *arg):	print("exec",key,arg)
	def missing(self,key):		print("key %s is missing", key)
	def corruption(self,key,*arg):	print("corrupt %s:" % key,arg)
	def eclass_stale(self,key,*arg):print("stale %s:"%key,arg)

