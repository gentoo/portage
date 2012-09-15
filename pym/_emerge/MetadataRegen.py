# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.dep import _repo_separator
from _emerge.EbuildMetadataPhase import EbuildMetadataPhase
from _emerge.PollScheduler import PollScheduler

class MetadataRegen(PollScheduler):

	def __init__(self, portdb, cp_iter=None, consumer=None,
		max_jobs=None, max_load=None, write_auxdb=True):
		PollScheduler.__init__(self, main=True)
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

		if max_jobs is None:
			max_jobs = 1

		self._max_jobs = max_jobs
		self._max_load = max_load

		self._valid_pkgs = set()
		self._cp_set = set()
		self._process_iter = self._iter_metadata_processes()
		self.returncode = os.EX_OK
		self._error_count = 0
		self._running_tasks = set()
		self._remaining_tasks = True

	def _terminate_tasks(self):
		for task in list(self._running_tasks):
			task.cancel()

	def _iter_every_cp(self):
		portage.writemsg_stdout("Listing available packages...\n")
		every_cp = self._portdb.cp_all()
		portage.writemsg_stdout("Regenerating cache entries...\n")
		every_cp.sort(reverse=True)
		try:
			while not self._terminated_tasks:
				yield every_cp.pop()
		except IndexError:
			pass

	def _iter_metadata_processes(self):
		portdb = self._portdb
		valid_pkgs = self._valid_pkgs
		cp_set = self._cp_set
		consumer = self._consumer

		for cp in self._cp_iter:
			if self._terminated_tasks:
				break
			cp_set.add(cp)
			portage.writemsg_stdout("Processing %s\n" % cp)
			# We iterate over portdb.porttrees, since it's common to
			# tweak this attribute in order to adjust repo selection.
			for mytree in portdb.porttrees:
				repo = portdb.repositories.get_repo_for_location(mytree)
				cpv_list = portdb.cp_list(cp, mytree=[repo.location])
				for cpv in cpv_list:
					if self._terminated_tasks:
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

	def _keep_scheduling(self):
		return self._remaining_tasks and not self._terminated_tasks

	def run(self):

		portdb = self._portdb
		from portage.cache.cache_errors import CacheError
		dead_nodes = {}

		self._main_loop()

		if self._terminated_tasks:
			self.returncode = 1
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

	def _schedule_tasks(self):
		if self._terminated_tasks:
			return

		while self._can_add_job():
			try:
				metadata_process = next(self._process_iter)
			except StopIteration:
				self._remaining_tasks = False
				return

			self._jobs += 1
			self._running_tasks.add(metadata_process)
			metadata_process.scheduler = self.sched_iface
			metadata_process.addExitListener(self._metadata_exit)
			metadata_process.start()

	def _metadata_exit(self, metadata_process):
		self._jobs -= 1
		self._running_tasks.discard(metadata_process)
		if metadata_process.returncode != os.EX_OK:
			self.returncode = 1
			self._error_count += 1
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

		self._schedule()

