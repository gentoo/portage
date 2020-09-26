# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.EbuildMetadataPhase import EbuildMetadataPhase

import portage
from portage import os
from portage.cache.cache_errors import CacheError
from portage.dep import _repo_separator
from portage.util._async.AsyncScheduler import AsyncScheduler

class MetadataRegen(AsyncScheduler):

	def __init__(self, portdb, cp_iter=None, consumer=None,
		write_auxdb=True, **kwargs):
		AsyncScheduler.__init__(self, **kwargs)
		self._portdb = portdb
		self._write_auxdb = write_auxdb
		self._global_cleanse = False
		if cp_iter is None:
			cp_iter = self._iter_every_cp()
			# We can globally cleanse stale cache only if we
			# iterate over every single cp.
			self._global_cleanse = True
		self._cp_iter = cp_iter
		self._consumer = consumer

		self._valid_pkgs = set()
		self._cp_set = set()
		self._process_iter = self._iter_metadata_processes()
		self._running_tasks = set()

	def _next_task(self):
		return next(self._process_iter)

	def _iter_every_cp(self):
		# List categories individually, in order to start yielding quicker,
		# and in order to reduce latency in case of a signal interrupt.
		cp_all = self._portdb.cp_all
		for category in sorted(self._portdb.categories):
			for cp in cp_all(categories=(category,)):
				yield cp

	def _iter_metadata_processes(self):
		portdb = self._portdb
		valid_pkgs = self._valid_pkgs
		cp_set = self._cp_set
		consumer = self._consumer

		portage.writemsg_stdout("Regenerating cache entries...\n")
		for cp in self._cp_iter:
			if self._terminated.is_set():
				break
			cp_set.add(cp)
			portage.writemsg_stdout("Processing %s\n" % cp)
			# We iterate over portdb.porttrees, since it's common to
			# tweak this attribute in order to adjust repo selection.
			for mytree in portdb.porttrees:
				repo = portdb.repositories.get_repo_for_location(mytree)
				cpv_list = portdb.cp_list(cp, mytree=[repo.location])
				for cpv in cpv_list:
					if self._terminated.is_set():
						break
					valid_pkgs.add(cpv)
					ebuild_path, repo_path = portdb.findname2(cpv, myrepo=repo.name)
					if ebuild_path is None:
						raise AssertionError("ebuild not found for '%s%s%s'" % (cpv, _repo_separator, repo.name))
					metadata, ebuild_hash = portdb._pull_valid_cache(
						cpv, ebuild_path, repo_path)
					if metadata is not None:
						if consumer is not None:
							consumer(cpv, repo_path, metadata, ebuild_hash, True)
						continue

					yield EbuildMetadataPhase(cpv=cpv,
						ebuild_hash=ebuild_hash,
						portdb=portdb, repo_path=repo_path,
						settings=portdb.doebuild_settings,
						write_auxdb=self._write_auxdb)

	def _cleanup(self):
		super(MetadataRegen, self)._cleanup()

		portdb = self._portdb
		dead_nodes = {}

		if self._terminated.is_set():
			portdb.flush_cache()
			return

		if self._global_cleanse:
			for mytree in portdb.porttrees:
				try:
					dead_nodes[mytree] = set(portdb.auxdb[mytree])
				except CacheError as e:
					portage.writemsg("Error listing cache entries for " + \
						"'%s': %s, continuing...\n" % (mytree, e),
						noiselevel=-1)
					del e
					dead_nodes = None
					break
		else:
			cp_set = self._cp_set
			cpv_getkey = portage.cpv_getkey
			for mytree in portdb.porttrees:
				try:
					dead_nodes[mytree] = set(cpv for cpv in \
						portdb.auxdb[mytree] \
						if cpv_getkey(cpv) in cp_set)
				except CacheError as e:
					portage.writemsg("Error listing cache entries for " + \
						"'%s': %s, continuing...\n" % (mytree, e),
						noiselevel=-1)
					del e
					dead_nodes = None
					break

		if dead_nodes:
			for y in self._valid_pkgs:
				for mytree in portdb.porttrees:
					if portdb.findname2(y, mytree=mytree)[0]:
						dead_nodes[mytree].discard(y)

			for mytree, nodes in dead_nodes.items():
				auxdb = portdb.auxdb[mytree]
				for y in nodes:
					try:
						del auxdb[y]
					except (KeyError, CacheError):
						pass

		portdb.flush_cache()

	def _task_exit(self, metadata_process):

		if metadata_process.returncode != os.EX_OK:
			self._valid_pkgs.discard(metadata_process.cpv)
			if not self._terminated_tasks:
				portage.writemsg("Error processing %s, continuing...\n" % \
					(metadata_process.cpv,), noiselevel=-1)

		if self._consumer is not None:
			# On failure, still notify the consumer (in this case the metadata
			# argument is None).
			self._consumer(metadata_process.cpv,
				metadata_process.repo_path,
				metadata_process.metadata,
				metadata_process.ebuild_hash,
				metadata_process.eapi_supported)

		AsyncScheduler._task_exit(self, metadata_process)
