# Copyright 2013-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import threading

from portage import os
from portage.checksum import (_apply_hash_filter,
	_filter_unaccelarated_hashes, _hash_filter)
from portage.dep import use_reduce
from portage.exception import PortageException, PortageKeyError
from portage.package.ebuild.fetch import DistfileName
from portage.util._async.AsyncTaskFuture import AsyncTaskFuture
from portage.util._async.TaskScheduler import TaskScheduler
from portage.util.futures.iter_completed import iter_gather
from .FetchTask import FetchTask
from _emerge.CompositeTask import CompositeTask


class FetchIterator:

	def __init__(self, config):
		self._config = config
		self._terminated = threading.Event()

	def terminate(self):
		"""
		Schedules early termination of the __iter__ method, which is
		useful because under some conditions it's possible for __iter__
		to loop for a long time without yielding to the caller. For
		example, it's useful when there are many ebuilds with stale
		cache and RESTRICT=mirror.

		This method is thread-safe (and safe for signal handlers).
		"""
		self._terminated.set()

	def _iter_every_cp(self):
		# List categories individually, in order to start yielding quicker,
		# and in order to reduce latency in case of a signal interrupt.
		cp_all = self._config.portdb.cp_all
		for category in sorted(self._config.portdb.categories):
			for cp in cp_all(categories=(category,)):
				yield cp

	def __iter__(self):

		portdb = self._config.portdb
		get_repo_for_location = portdb.repositories.get_repo_for_location

		hash_filter = _hash_filter(
			portdb.settings.get("PORTAGE_CHECKSUM_FILTER", ""))
		if hash_filter.transparent:
			hash_filter = None

		for cp in self._iter_every_cp():

			if self._terminated.is_set():
				return

			for tree in portdb.porttrees:

				# Reset state so the Manifest is pulled once
				# for this cp / tree combination.
				repo_config = get_repo_for_location(tree)
				digests_future = portdb._event_loop.create_future()

				for cpv in portdb.cp_list(cp, mytree=tree):

					if self._terminated.is_set():
						return

					yield _EbuildFetchTasks(
						fetch_tasks_future=_async_fetch_tasks(
							self._config,
							hash_filter,
							repo_config,
							digests_future,
							cpv,
							portdb._event_loop)
					)


class _EbuildFetchTasks(CompositeTask):
	"""
	Executes FetchTask instances (which are asynchronously constructed)
	for each of the files referenced by an ebuild.
	"""
	__slots__ = ('fetch_tasks_future',)
	def _start(self):
		self._start_task(AsyncTaskFuture(future=self.fetch_tasks_future),
			self._start_fetch_tasks)

	def _start_fetch_tasks(self, task):
		if self._default_exit(task) != os.EX_OK:
			self._async_wait()
			return

		self._start_task(
			TaskScheduler(
				iter(self.fetch_tasks_future.result()),
				max_jobs=1,
				event_loop=self.scheduler),
			self._default_final_exit)


def _async_fetch_tasks(config, hash_filter, repo_config, digests_future, cpv,
	loop):
	"""
	Asynchronously construct FetchTask instances for each of the files
	referenced by an ebuild.

	@param config: emirrordist config
	@type config: portage._emirrordist.Config.Config
	@param hash_filter: PORTAGE_CHECKSUM_FILTER settings
	@type hash_filter: portage.checksum._hash_filter
	@param repo_config: repository configuration
	@type repo_config: RepoConfig
	@param digests_future: future that contains cached distfiles digests
		for the current cp if available
	@type digests_future: asyncio.Future
	@param cpv: current ebuild cpv
	@type cpv: portage.versions._pkg_str
	@param loop: event loop
	@type loop: EventLoop
	@return: A future that results in a list containing FetchTask
		instances for each of the files referenced by an ebuild.
	@rtype: asyncio.Future (or compatible)
	"""
	result = loop.create_future()
	fetch_tasks = []

	def aux_get_done(gather_result):
		# All exceptions must be consumed from gather_result before this
		# function returns, in order to avoid triggering the event loop's
		# exception handler.
		if not gather_result.cancelled():
			list(future.exception() for future in gather_result.result()
				if not future.cancelled())
		else:
			result.cancel()

		if result.cancelled():
			return

		aux_get_result, fetch_map_result = gather_result.result()
		if aux_get_result.cancelled() or fetch_map_result.cancelled():
			# Cancel result after consuming any exceptions which
			# are now irrelevant due to cancellation.
			aux_get_result.cancelled() or aux_get_result.exception()
			fetch_map_result.cancelled() or fetch_map_result.exception()
			result.cancel()
			return

		try:
			restrict, = aux_get_result.result()
		except (PortageKeyError, PortageException) as e:
			config.log_failure("%s\t\taux_get exception %s" %
				(cpv, e))
			result.set_result(fetch_tasks)
			return

		# Here we use matchnone=True to ignore conditional parts
		# of RESTRICT since they don't apply unconditionally.
		# Assume such conditionals only apply on the client side.
		try:
			restrict = frozenset(use_reduce(restrict,
				flat=True, matchnone=True))
		except PortageException as e:
			config.log_failure("%s\t\tuse_reduce exception %s" %
				(cpv, e))
			result.set_result(fetch_tasks)
			return

		try:
			uri_map = fetch_map_result.result()
		except PortageException as e:
			config.log_failure("%s\t\tgetFetchMap exception %s" %
				(cpv, e))
			result.set_result(fetch_tasks)
			return

		if not uri_map:
			result.set_result(fetch_tasks)
			return

		new_uri_map = {}
		restrict_fetch = "fetch" in restrict
		restrict_mirror = restrict_fetch or "mirror" in restrict
		for filename, uri_tuple in uri_map.items():
			new_uris = []
			for uri in uri_tuple:
				override_mirror = uri.startswith("mirror+")
				override_fetch = override_mirror or uri.startswith("fetch+")
				if override_fetch:
					uri = uri.partition("+")[2]

				# skip fetch-restricted files unless overriden via fetch+
				# or mirror+
				if restrict_fetch and not override_fetch:
					continue
				# skip mirror-restricted files unless override via mirror+
				# or in config_mirror_exemptions
				if restrict_mirror and not override_mirror:
					if (config.restrict_mirror_exemptions is None or
							not uri.startswith("mirror://")):
						continue
					mirror_name = uri.split('/', 3)[2]
					if mirror_name not in config.restrict_mirror_exemptions:
						continue
				# if neither fetch or mirror restriction applies to the URI
				# or it is exempted from them, readd it (with fetch+/mirror+
				# prefix stripped)
				new_uris.append(uri)

			# if we've gotten any new URIs, then we readd the file
			if new_uris:
				new_uri_map[filename] = new_uris

		if not new_uri_map:
			result.set_result(fetch_tasks)
			return

		# Parse Manifest for this cp if we haven't yet.
		try:
			if digests_future.done():
				# If there's an exception then raise it.
				digests = digests_future.result()
			else:
				digests = repo_config.load_manifest(
					os.path.join(repo_config.location, cpv.cp)).\
					getTypeDigests("DIST")
		except (EnvironmentError, PortageException) as e:
			digests_future.done() or digests_future.set_exception(e)
			for filename in new_uri_map:
				config.log_failure(
					"%s\t%s\tManifest exception %s" %
					(cpv, filename, e))
				config.file_failures[filename] = cpv
			result.set_result(fetch_tasks)
			return
		else:
			digests_future.done() or digests_future.set_result(digests)

		if not digests:
			for filename in new_uri_map:
				config.log_failure("%s\t%s\tdigest entry missing" %
					(cpv, filename))
				config.file_failures[filename] = cpv
			result.set_result(fetch_tasks)
			return

		for filename, uri_tuple in new_uri_map.items():
			file_digests = digests.get(filename)
			if file_digests is None:
				config.log_failure("%s\t%s\tdigest entry missing" %
					(cpv, filename))
				config.file_failures[filename] = cpv
				continue
			if filename in config.file_owners:
				continue
			config.file_owners[filename] = cpv

			file_digests = \
				_filter_unaccelarated_hashes(file_digests)
			if hash_filter is not None:
				file_digests = _apply_hash_filter(
					file_digests, hash_filter)

			fetch_tasks.append(FetchTask(
				cpv=cpv,
				background=True,
				digests=file_digests,
				distfile=DistfileName(filename, digests=file_digests),
				restrict=restrict,
				uri_tuple=uri_tuple,
				config=config))

		result.set_result(fetch_tasks)

	def future_generator():
		yield config.portdb.async_aux_get(cpv, ("RESTRICT",),
			myrepo=repo_config.name, loop=loop)
		yield config.portdb.async_fetch_map(cpv,
			mytree=repo_config.location, loop=loop)

	# Use iter_gather(max_jobs=1) to limit the number of processes per
	# _EbuildFetchTask instance, and also to avoid spawning two bash
	# processes for the same cpv simultaneously (the second one can
	# use metadata cached by the first one).
	gather_result = iter_gather(
		future_generator(),
		max_jobs=1,
		loop=loop,
	)
	gather_result.add_done_callback(aux_get_done)
	result.add_done_callback(lambda result:
		gather_result.cancel() if result.cancelled() and
		not gather_result.done() else None)

	return result
