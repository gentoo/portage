# Copyright 1998-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
import operator
import sys
import signal

from _emerge.ProgressHandler import ProgressHandler

import portage
from portage import eapi_is_supported
from portage import os
from portage.cache.cache_errors import CacheError
from portage.eclass_cache import hashed_path
from portage.util import writemsg_level

def action_metadata(settings, portdb, myopts, porttrees=None):
	if porttrees is None:
		porttrees = portdb.porttrees
	portage.writemsg_stdout("\n>>> Updating Portage cache\n")
	cachedir = os.path.normpath(settings.depcachedir)
	if cachedir in ["/",    "/bin", "/dev",  "/etc",  "/home",
					"/lib", "/opt", "/proc", "/root", "/sbin",
					"/sys", "/tmp", "/usr",  "/var"]:
		print("!!! PORTAGE_DEPCACHEDIR IS SET TO A PRIMARY " + \
			"ROOT DIRECTORY ON YOUR SYSTEM.", file=sys.stderr)
		print("!!! This is ALMOST CERTAINLY NOT what you want: '%s'" % cachedir, file=sys.stderr)
		sys.exit(73)
	if not os.path.exists(cachedir):
		os.makedirs(cachedir)

	auxdbkeys = portdb._known_keys

	class TreeData:
		__slots__ = ('dest_db', 'eclass_db', 'path', 'src_db', 'valid_nodes')
		def __init__(self, dest_db, eclass_db, path, src_db):
			self.dest_db = dest_db
			self.eclass_db = eclass_db
			self.path = path
			self.src_db = src_db
			self.valid_nodes = set()

	porttrees_data = []
	for path in porttrees:
		src_db = portdb._pregen_auxdb.get(path)
		if src_db is None:
			# portdbapi does not populate _pregen_auxdb
			# when FEATURES=metadata-transfer is enabled
			src_db = portdb._create_pregen_cache(path)

		if src_db is not None:
			eclass_db = portdb.repositories.get_repo_for_location(path).eclass_db
			# Update eclass data which may be stale after sync.
			eclass_db.update_eclasses()
			porttrees_data.append(TreeData(portdb.auxdb[path], eclass_db, path, src_db))

	porttrees = [tree_data.path for tree_data in porttrees_data]

	quiet = settings.get('TERM') == 'dumb' or \
		'--quiet' in myopts or \
		not sys.stdout.isatty()

	onProgress = None
	if not quiet:
		progressBar = portage.output.TermProgressBar()
		progressHandler = ProgressHandler()
		onProgress = progressHandler.onProgress
		def display():
			progressBar.set(progressHandler.curval, progressHandler.maxval)
		progressHandler.display = display
		def sigwinch_handler(signum, frame):
			lines, progressBar.term_columns = \
				portage.output.get_term_size()
		signal.signal(signal.SIGWINCH, sigwinch_handler)

	# Temporarily override portdb.porttrees so portdb.cp_all()
	# will only return the relevant subset.
	portdb_porttrees = portdb.porttrees
	portdb.porttrees = porttrees
	try:
		cp_all = portdb.cp_all()
	finally:
		portdb.porttrees = portdb_porttrees

	curval = 0
	maxval = len(cp_all)
	if onProgress is not None:
		onProgress(maxval, curval)

	# TODO: Display error messages, but do not interfere with the progress bar.
	# Here's how:
	#  1) erase the progress bar
	#  2) show the error message
	#  3) redraw the progress bar on a new line

	for cp in cp_all:
		for tree_data in porttrees_data:

			src_chf = tree_data.src_db.validation_chf
			dest_chf = tree_data.dest_db.validation_chf
			dest_chf_key = '_%s_' % dest_chf
			dest_chf_getter = operator.attrgetter(dest_chf)

			for cpv in portdb.cp_list(cp, mytree=tree_data.path):
				tree_data.valid_nodes.add(cpv)
				try:
					src = tree_data.src_db[cpv]
				except (CacheError, KeyError):
					continue

				ebuild_location = portdb.findname(cpv, mytree=tree_data.path)
				if ebuild_location is None:
					continue
				ebuild_hash = hashed_path(ebuild_location)

				try:
					if not tree_data.src_db.validate_entry(src,
						ebuild_hash, tree_data.eclass_db):
						continue
				except CacheError:
					continue

				eapi = src.get('EAPI')
				if not eapi:
					eapi = '0'
				eapi_supported = eapi_is_supported(eapi)
				if not eapi_supported:
					continue

				dest = None
				try:
					dest = tree_data.dest_db[cpv]
				except (KeyError, CacheError):
					pass

				for d in (src, dest):
					if d is not None and d.get('EAPI') in ('', '0'):
						del d['EAPI']

				if src_chf != 'mtime':
					# src may contain an irrelevant _mtime_ which corresponds
					# to the time that the cache entry was written
					src.pop('_mtime_', None)

				if src_chf != dest_chf:
					# populate src entry with dest_chf_key
					# (the validity of the dest_chf that we generate from the
					# ebuild here relies on the fact that we already used
					# validate_entry to validate the ebuild with src_chf)
					src[dest_chf_key] = dest_chf_getter(ebuild_hash)

				if dest is not None:
					if not (dest.get(dest_chf_key) == src[dest_chf_key] and \
						tree_data.eclass_db.validate_and_rewrite_cache(
							dest['_eclasses_'], tree_data.dest_db.validation_chf,
							tree_data.dest_db.store_eclass_paths) is not None and \
						set(dest['_eclasses_']) == set(src['_eclasses_'])):
						dest = None
					else:
						# We don't want to skip the write unless we're really
						# sure that the existing cache is identical, so don't
						# trust _mtime_ and _eclasses_ alone.
						for k in auxdbkeys:
							if dest.get(k, '') != src.get(k, ''):
								dest = None
								break

				if dest is not None:
					# The existing data is valid and identical,
					# so there's no need to overwrite it.
					continue

				try:
					tree_data.dest_db[cpv] = src
				except CacheError:
					# ignore it; can't do anything about it.
					pass

		curval += 1
		if onProgress is not None:
			onProgress(maxval, curval)

	if onProgress is not None:
		onProgress(maxval, curval)

	for tree_data in porttrees_data:
		try:
			dead_nodes = set(tree_data.dest_db)
		except CacheError as e:
			writemsg_level("Error listing cache entries for " + \
				"'%s': %s, continuing...\n" % (tree_data.path, e),
				level=logging.ERROR, noiselevel=-1)
			del e
		else:
			dead_nodes.difference_update(tree_data.valid_nodes)
			for cpv in dead_nodes:
				try:
					del tree_data.dest_db[cpv]
				except (KeyError, CacheError):
					pass

	if not quiet:
		# make sure the final progress is displayed
		progressHandler.display()
		print()
		signal.signal(signal.SIGWINCH, signal.SIG_DFL)

	portdb.flush_cache()
	sys.stdout.flush()
