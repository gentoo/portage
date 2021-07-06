# Copyright 1999-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from collections import deque
import gc
import gzip
import logging
import signal
import sys
import textwrap
import time
import warnings
import weakref
import zlib

import portage
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.cache.mappings import slot_dict_class
from portage.elog.messages import eerror
from portage.output import colorize, create_color_func, red
bad = create_color_func("BAD")
from portage._sets import SETPREFIX
from portage._sets.base import InternalPackageSet
from portage.util import ensure_dirs, writemsg, writemsg_level
from portage.util.futures import asyncio
from portage.util.SlotObject import SlotObject
from portage.util._async.SchedulerInterface import SchedulerInterface
from portage.package.ebuild.digestcheck import digestcheck
from portage.package.ebuild.digestgen import digestgen
from portage.package.ebuild.doebuild import (_check_temp_dir,
	_prepare_self_update)
from portage.package.ebuild.prepare_build_dirs import prepare_build_dirs

import _emerge
from _emerge.BinpkgFetcher import BinpkgFetcher
from _emerge.BinpkgPrefetcher import BinpkgPrefetcher
from _emerge.BinpkgVerifier import BinpkgVerifier
from _emerge.Blocker import Blocker
from _emerge.BlockerDB import BlockerDB
from _emerge.clear_caches import clear_caches
from _emerge.create_depgraph_params import create_depgraph_params
from _emerge.create_world_atom import create_world_atom
from _emerge.DepPriority import DepPriority
from _emerge.depgraph import depgraph, resume_depgraph
from _emerge.EbuildBuildDir import EbuildBuildDir
from _emerge.EbuildFetcher import EbuildFetcher
from _emerge.EbuildPhase import EbuildPhase
from _emerge.emergelog import emergelog
from _emerge.FakeVartree import FakeVartree
from _emerge.getloadavg import getloadavg
from _emerge._find_deep_system_runtime_deps import _find_deep_system_runtime_deps
from _emerge._flush_elog_mod_echo import _flush_elog_mod_echo
from _emerge.JobStatusDisplay import JobStatusDisplay
from _emerge.MergeListItem import MergeListItem
from _emerge.Package import Package
from _emerge.PackageMerge import PackageMerge
from _emerge.PollScheduler import PollScheduler
from _emerge.SequentialTaskQueue import SequentialTaskQueue

# enums
FAILURE = 1


class Scheduler(PollScheduler):

	# max time between loadavg checks (seconds)
	_loadavg_latency = 30

	# max time between display status updates (seconds)
	_max_display_latency = 3

	_opts_ignore_blockers = \
		frozenset(["--buildpkgonly",
		"--fetchonly", "--fetch-all-uri",
		"--nodeps", "--pretend"])

	_opts_no_background = \
		frozenset(["--pretend",
		"--fetchonly", "--fetch-all-uri"])

	_opts_no_self_update = frozenset(["--buildpkgonly",
		"--fetchonly", "--fetch-all-uri", "--pretend"])

	class _iface_class(SchedulerInterface):
		__slots__ = ("fetch",
			"scheduleSetup", "scheduleUnpack")

	class _fetch_iface_class(SlotObject):
		__slots__ = ("log_file", "schedule")

	_task_queues_class = slot_dict_class(
		("merge", "jobs", "ebuild_locks", "fetch", "unpack"), prefix="")

	class _build_opts_class(SlotObject):
		__slots__ = ("buildpkg", "buildpkg_exclude", "buildpkgonly",
			"fetch_all_uri", "fetchonly", "pretend")

	class _binpkg_opts_class(SlotObject):
		__slots__ = ("fetchonly", "getbinpkg", "pretend")

	class _pkg_count_class(SlotObject):
		__slots__ = ("curval", "maxval")

	class _emerge_log_class(SlotObject):
		__slots__ = ("xterm_titles",)

		def log(self, *pargs, **kwargs):
			if not self.xterm_titles:
				# Avoid interference with the scheduler's status display.
				kwargs.pop("short_msg", None)
			emergelog(self.xterm_titles, *pargs, **kwargs)

	class _failed_pkg(SlotObject):
		__slots__ = ("build_dir", "build_log", "pkg",
			"postinst_failure", "returncode")

	class _ConfigPool:
		"""Interface for a task to temporarily allocate a config
		instance from a pool. This allows a task to be constructed
		long before the config instance actually becomes needed, like
		when prefetchers are constructed for the whole merge list."""
		__slots__ = ("_root", "_allocate", "_deallocate")
		def __init__(self, root, allocate, deallocate):
			self._root = root
			self._allocate = allocate
			self._deallocate = deallocate
		def allocate(self):
			return self._allocate(self._root)
		def deallocate(self, settings):
			self._deallocate(settings)

	class _unknown_internal_error(portage.exception.PortageException):
		"""
		Used internally to terminate scheduling. The specific reason for
		the failure should have been dumped to stderr.
		"""
		def __init__(self, value=""):
			portage.exception.PortageException.__init__(self, value)

	def __init__(self, settings, trees, mtimedb, myopts,
		spinner, mergelist=None, favorites=None, graph_config=None):
		PollScheduler.__init__(self, main=True)

		if mergelist is not None:
			warnings.warn("The mergelist parameter of the " + \
				"_emerge.Scheduler constructor is now unused. Use " + \
				"the graph_config parameter instead.",
				DeprecationWarning, stacklevel=2)

		self.settings = settings
		self.target_root = settings["EROOT"]
		self.trees = trees
		self.myopts = myopts
		self._spinner = spinner
		self._mtimedb = mtimedb
		self._favorites = favorites
		self._args_set = InternalPackageSet(favorites, allow_repo=True)
		self._build_opts = self._build_opts_class()

		for k in self._build_opts.__slots__:
			setattr(self._build_opts, k, myopts.get("--" + k.replace("_", "-")))
		self._build_opts.buildpkg_exclude = InternalPackageSet( \
			initial_atoms=" ".join(myopts.get("--buildpkg-exclude", [])).split(), \
			allow_wildcard=True, allow_repo=True)
		if "mirror" in self.settings.features:
			self._build_opts.fetch_all_uri = True

		self._binpkg_opts = self._binpkg_opts_class()
		for k in self._binpkg_opts.__slots__:
			setattr(self._binpkg_opts, k, "--" + k.replace("_", "-") in myopts)

		self.curval = 0
		self._logger = self._emerge_log_class()
		self._task_queues = self._task_queues_class()
		for k in self._task_queues.allowed_keys:
			setattr(self._task_queues, k,
				SequentialTaskQueue())

		# Holds merges that will wait to be executed when no builds are
		# executing. This is useful for system packages since dependencies
		# on system packages are frequently unspecified. For example, see
		# bug #256616.
		self._merge_wait_queue = deque()
		# Holds merges that have been transfered from the merge_wait_queue to
		# the actual merge queue. They are removed from this list upon
		# completion. Other packages can start building only when this list is
		# empty.
		self._merge_wait_scheduled = []

		# Holds system packages and their deep runtime dependencies. Before
		# being merged, these packages go to merge_wait_queue, to be merged
		# when no other packages are building.
		self._deep_system_deps = set()

		# Holds packages to merge which will satisfy currently unsatisfied
		# deep runtime dependencies of system packages. If this is not empty
		# then no parallel builds will be spawned until it is empty. This
		# minimizes the possibility that a build will fail due to the system
		# being in a fragile state. For example, see bug #259954.
		self._unsatisfied_system_deps = set()

		self._status_display = JobStatusDisplay(
			xterm_titles=('notitles' not in settings.features))
		self._max_load = myopts.get("--load-average")
		max_jobs = myopts.get("--jobs")
		if max_jobs is None:
			max_jobs = 1
		self._set_max_jobs(max_jobs)
		self._running_root = trees[trees._running_eroot]["root_config"]
		self.edebug = 0
		if settings.get("PORTAGE_DEBUG", "") == "1":
			self.edebug = 1
		self.pkgsettings = {}
		self._config_pool = {}
		for root in self.trees:
			self._config_pool[root] = []

		self._fetch_log = os.path.join(_emerge.emergelog._emerge_log_dir,
			'emerge-fetch.log')
		fetch_iface = self._fetch_iface_class(log_file=self._fetch_log,
			schedule=self._schedule_fetch)
		self._sched_iface = self._iface_class(
			self._event_loop,
			is_background=self._is_background,
			fetch=fetch_iface,
			scheduleSetup=self._schedule_setup,
			scheduleUnpack=self._schedule_unpack)

		self._prefetchers = weakref.WeakValueDictionary()
		self._pkg_queue = []
		self._jobs = 0
		self._running_tasks = {}
		self._completed_tasks = set()
		self._main_exit = None
		self._main_loadavg_handle = None
		self._schedule_merge_wakeup_task = None

		self._failed_pkgs = []
		self._failed_pkgs_all = []
		self._failed_pkgs_die_msgs = []
		self._post_mod_echo_msgs = []
		self._parallel_fetch = False
		self._init_graph(graph_config)
		merge_count = len([x for x in self._mergelist \
			if isinstance(x, Package) and x.operation == "merge"])
		self._pkg_count = self._pkg_count_class(
			curval=0, maxval=merge_count)
		self._status_display.maxval = self._pkg_count.maxval

		# The load average takes some time to respond when new
		# jobs are added, so we need to limit the rate of adding
		# new jobs.
		self._job_delay_max = 5
		self._previous_job_start_time = None
		self._job_delay_timeout_id = None

		# The load average takes some time to respond when after
		# a SIGSTOP/SIGCONT cycle, so delay scheduling for some
		# time after SIGCONT is received.
		self._sigcont_delay = 5
		self._sigcont_time = None

		# This is used to memoize the _choose_pkg() result when
		# no packages can be chosen until one of the existing
		# jobs completes.
		self._choose_pkg_return_early = False

		features = self.settings.features
		if "parallel-fetch" in features and \
			not ("--pretend" in self.myopts or \
			"--fetch-all-uri" in self.myopts or \
			"--fetchonly" in self.myopts):
			if "distlocks" not in features:
				portage.writemsg(red("!!!")+"\n", noiselevel=-1)
				portage.writemsg(red("!!!")+" parallel-fetching " + \
					"requires the distlocks feature enabled"+"\n",
					noiselevel=-1)
				portage.writemsg(red("!!!")+" you have it disabled, " + \
					"thus parallel-fetching is being disabled"+"\n",
					noiselevel=-1)
				portage.writemsg(red("!!!")+"\n", noiselevel=-1)
			elif merge_count > 1:
				self._parallel_fetch = True

		if self._parallel_fetch:
			# clear out existing fetch log if it exists
			try:
				open(self._fetch_log, 'w').close()
			except EnvironmentError:
				pass

		self._running_portage = None
		portage_match = self._running_root.trees["vartree"].dbapi.match(
			portage.const.PORTAGE_PACKAGE_ATOM)
		if portage_match:
			cpv = portage_match.pop()
			self._running_portage = self._pkg(cpv, "installed",
				self._running_root, installed=True)

	def _handle_self_update(self):

		if self._opts_no_self_update.intersection(self.myopts):
			return os.EX_OK

		for x in self._mergelist:
			if not isinstance(x, Package):
				continue
			if x.operation != "merge":
				continue
			if x.root != self._running_root.root:
				continue
			if not portage.dep.match_from_list(
				portage.const.PORTAGE_PACKAGE_ATOM, [x]):
				continue
			rval = _check_temp_dir(self.settings)
			if rval != os.EX_OK:
				return rval
			_prepare_self_update(self.settings)
			break

		return os.EX_OK

	def _terminate_tasks(self):
		self._status_display.quiet = True
		for task in list(self._running_tasks.values()):
			if task.isAlive():
				# This task should keep the main loop running until
				# it has had an opportunity to clean up after itself.
				# Rely on its exit hook to remove it from
				# self._running_tasks when it has finished cleaning up.
				task.cancel()
			else:
				# This task has been waiting to be started in one of
				# self._task_queues which are all cleared below. It
				# will never be started, so purged it from
				# self._running_tasks so that it won't keep the main
				# loop running.
				del self._running_tasks[id(task)]

		for q in self._task_queues.values():
			q.clear()

	def _init_graph(self, graph_config):
		"""
		Initialization structures used for dependency calculations
		involving currently installed packages.
		"""
		self._set_graph_config(graph_config)
		self._blocker_db = {}
		depgraph_params = create_depgraph_params(self.myopts, None)
		dynamic_deps = "dynamic_deps" in depgraph_params
		ignore_built_slot_operator_deps = self.myopts.get(
			"--ignore-built-slot-operator-deps", "n") == "y"
		for root in self.trees:
			if graph_config is None:
				fake_vartree = FakeVartree(self.trees[root]["root_config"],
					pkg_cache=self._pkg_cache, dynamic_deps=dynamic_deps,
					ignore_built_slot_operator_deps=ignore_built_slot_operator_deps)
				fake_vartree.sync()
			else:
				fake_vartree = graph_config.trees[root]['vartree']
			self._blocker_db[root] = BlockerDB(fake_vartree)

	def _destroy_graph(self):
		"""
		Use this to free memory at the beginning of _calc_resume_list().
		After _calc_resume_list(), the _init_graph() method
		must to be called in order to re-generate the structures that
		this method destroys.
		"""
		self._blocker_db = None
		self._set_graph_config(None)
		gc.collect()

	def _set_max_jobs(self, max_jobs):
		self._max_jobs = max_jobs
		self._task_queues.jobs.max_jobs = max_jobs
		if "parallel-install" in self.settings.features:
			self._task_queues.merge.max_jobs = max_jobs

	def _background_mode(self):
		"""
		Check if background mode is enabled and adjust states as necessary.

		@rtype: bool
		@return: True if background mode is enabled, False otherwise.
		"""
		background = (self._max_jobs is True or \
			self._max_jobs > 1 or "--quiet" in self.myopts \
			or self.myopts.get("--quiet-build") == "y") and \
			not bool(self._opts_no_background.intersection(self.myopts))

		if background:
			interactive_tasks = self._get_interactive_tasks()
			if interactive_tasks:
				background = False
				writemsg_level(">>> Sending package output to stdio due " + \
					"to interactive package(s):\n",
					level=logging.INFO, noiselevel=-1)
				msg = [""]
				for pkg in interactive_tasks:
					pkg_str = "  " + colorize("INFORM", str(pkg.cpv))
					if pkg.root_config.settings["ROOT"] != "/":
						pkg_str += " for " + pkg.root
					msg.append(pkg_str)
				msg.append("")
				writemsg_level("".join("%s\n" % (l,) for l in msg),
					level=logging.INFO, noiselevel=-1)
				if self._max_jobs is True or self._max_jobs > 1:
					self._set_max_jobs(1)
					writemsg_level(">>> Setting --jobs=1 due " + \
						"to the above interactive package(s)\n",
						level=logging.INFO, noiselevel=-1)
					writemsg_level(">>> In order to temporarily mask " + \
						"interactive updates, you may\n" + \
						">>> specify --accept-properties=-interactive\n",
						level=logging.INFO, noiselevel=-1)
		self._status_display.quiet = \
			not background or \
			("--quiet" in self.myopts and \
			"--verbose" not in self.myopts)

		self._logger.xterm_titles = \
			"notitles" not in self.settings.features and \
			self._status_display.quiet

		return background

	def _get_interactive_tasks(self):
		interactive_tasks = []
		for task in self._mergelist:
			if not (isinstance(task, Package) and \
				task.operation == "merge"):
				continue
			if 'interactive' in task.properties:
				interactive_tasks.append(task)
		return interactive_tasks

	def _set_graph_config(self, graph_config):

		if graph_config is None:
			self._graph_config = None
			self._pkg_cache = {}
			self._digraph = None
			self._mergelist = []
			self._world_atoms = None
			self._deep_system_deps.clear()
			return

		self._graph_config = graph_config
		self._pkg_cache = graph_config.pkg_cache
		self._digraph = graph_config.graph
		self._mergelist = graph_config.mergelist

		# Generate world atoms while the event loop is not running,
		# since otherwise portdbapi match calls in the create_world_atom
		# function could trigger event loop recursion.
		self._world_atoms = {}
		for pkg in self._mergelist:
			if getattr(pkg, 'operation', None) != 'merge':
				continue
			atom = create_world_atom(pkg, self._args_set,
				pkg.root_config, before_install=True)
			if atom is not None:
				self._world_atoms[pkg] = atom

		if "--nodeps" in self.myopts or \
			(self._max_jobs is not True and self._max_jobs < 2):
			# save some memory
			self._digraph = None
			graph_config.graph = None
			graph_config.pkg_cache.clear()
			self._deep_system_deps.clear()
			for pkg in self._mergelist:
				self._pkg_cache[pkg] = pkg
			return

		self._find_system_deps()
		self._prune_digraph()
		self._prevent_builddir_collisions()
		if '--debug' in self.myopts:
			writemsg("\nscheduler digraph:\n\n", noiselevel=-1)
			self._digraph.debug_print()
			writemsg("\n", noiselevel=-1)

	def _find_system_deps(self):
		"""
		Find system packages and their deep runtime dependencies. Before being
		merged, these packages go to merge_wait_queue, to be merged when no
		other packages are building.
		NOTE: This can only find deep system deps if the system set has been
		added to the graph and traversed deeply (the depgraph "complete"
		parameter will do this, triggered by emerge --complete-graph option).
		"""
		params = create_depgraph_params(self.myopts, None)
		if not params["implicit_system_deps"]:
			return

		deep_system_deps = self._deep_system_deps
		deep_system_deps.clear()
		deep_system_deps.update(
			_find_deep_system_runtime_deps(self._digraph))
		deep_system_deps.difference_update([pkg for pkg in \
			deep_system_deps if pkg.operation != "merge"])

	def _prune_digraph(self):
		"""
		Prune any root nodes that are irrelevant.
		"""

		graph = self._digraph
		completed_tasks = self._completed_tasks
		removed_nodes = set()
		while True:
			for node in graph.root_nodes():
				if not isinstance(node, Package) or \
					(node.installed and node.operation == "nomerge") or \
					node.onlydeps or \
					node in completed_tasks:
					removed_nodes.add(node)
			if removed_nodes:
				graph.difference_update(removed_nodes)
			if not removed_nodes:
				break
			removed_nodes.clear()

	def _prevent_builddir_collisions(self):
		"""
		When building stages, sometimes the same exact cpv needs to be merged
		to both $ROOTs. Add edges to the digraph in order to avoid collisions
		in the builddir. Currently, normal file locks would be inappropriate
		for this purpose since emerge holds all of it's build dir locks from
		the main process.
		"""
		cpv_map = {}
		for pkg in self._mergelist:
			if not isinstance(pkg, Package):
				# a satisfied blocker
				continue
			if pkg.installed:
				continue
			if pkg.cpv not in cpv_map:
				cpv_map[pkg.cpv] = [pkg]
				continue
			for earlier_pkg in cpv_map[pkg.cpv]:
				self._digraph.add(earlier_pkg, pkg,
					priority=DepPriority(buildtime=True))
			cpv_map[pkg.cpv].append(pkg)

	class _pkg_failure(portage.exception.PortageException):
		"""
		An instance of this class is raised by unmerge() when
		an uninstallation fails.
		"""
		status = 1
		def __init__(self, *pargs):
			portage.exception.PortageException.__init__(self, pargs)
			if pargs:
				self.status = pargs[0]

	def _schedule_fetch(self, fetcher, force_queue=False):
		"""
		Schedule a fetcher, in order to control the number of concurrent
		fetchers. If self._max_jobs is greater than 1 then the fetch
		queue is bypassed and the fetcher is started immediately,
		otherwise it is added to the front of the parallel-fetch queue.
		NOTE: The parallel-fetch queue is currently used to serialize
		access to the parallel-fetch log, so changes in the log handling
		would be required before it would be possible to enable
		concurrent fetching within the parallel-fetch queue.
		"""
		if self._max_jobs > 1 and not force_queue:
			fetcher.start()
		else:
			self._task_queues.fetch.addFront(fetcher)

	def _schedule_setup(self, setup_phase):
		"""
		Schedule a setup phase on the merge queue, in order to
		serialize unsandboxed access to the live filesystem.
		"""
		if self._task_queues.merge.max_jobs > 1 and \
			"ebuild-locks" in self.settings.features:
			# Use a separate queue for ebuild-locks when the merge
			# queue allows more than 1 job (due to parallel-install),
			# since the portage.locks module does not behave as desired
			# if we try to lock the same file multiple times
			# concurrently from the same process.
			self._task_queues.ebuild_locks.add(setup_phase)
		else:
			self._task_queues.merge.add(setup_phase)
		self._schedule()

	def _schedule_unpack(self, unpack_phase):
		"""
		Schedule an unpack phase on the unpack queue, in order
		to serialize $DISTDIR access for live ebuilds.
		"""
		self._task_queues.unpack.add(unpack_phase)

	def _find_blockers(self, new_pkg):
		"""
		Returns a callable.
		"""
		def get_blockers():
			return self._find_blockers_impl(new_pkg)
		return get_blockers

	def _find_blockers_impl(self, new_pkg):
		if self._opts_ignore_blockers.intersection(self.myopts):
			return None

		blocker_db = self._blocker_db[new_pkg.root]

		blocked_pkgs = []
		for blocking_pkg in blocker_db.findInstalledBlockers(new_pkg):
			if new_pkg.slot_atom == blocking_pkg.slot_atom:
				continue
			if new_pkg.cpv == blocking_pkg.cpv:
				continue
			blocked_pkgs.append(blocking_pkg)

		return blocked_pkgs

	def _generate_digests(self):
		"""
		Generate digests if necessary for --digests or FEATURES=digest.
		In order to avoid interference, this must done before parallel
		tasks are started.
		"""

		digest = '--digest' in self.myopts
		if not digest:
			for pkgsettings in self.pkgsettings.values():
				if pkgsettings.mycpv is not None:
					# ensure that we are using global features
					# settings rather than those from package.env
					pkgsettings.reset()
				if 'digest' in pkgsettings.features:
					digest = True
					break

		if not digest:
			return os.EX_OK

		for x in self._mergelist:
			if not isinstance(x, Package) or \
				x.type_name != 'ebuild' or \
				x.operation != 'merge':
				continue
			pkgsettings = self.pkgsettings[x.root]
			if pkgsettings.mycpv is not None:
				# ensure that we are using global features
				# settings rather than those from package.env
				pkgsettings.reset()
			if '--digest' not in self.myopts and \
				'digest' not in pkgsettings.features:
				continue
			portdb = x.root_config.trees['porttree'].dbapi
			ebuild_path = portdb.findname(x.cpv, myrepo=x.repo)
			if ebuild_path is None:
				raise AssertionError("ebuild not found for '%s'" % x.cpv)
			pkgsettings['O'] = os.path.dirname(ebuild_path)
			if not digestgen(mysettings=pkgsettings, myportdb=portdb):
				writemsg_level(
					"!!! Unable to generate manifest for '%s'.\n" \
					% x.cpv, level=logging.ERROR, noiselevel=-1)
				return FAILURE

		return os.EX_OK

	def _check_manifests(self):
		# Verify all the manifests now so that the user is notified of failure
		# as soon as possible.
		if "strict" not in self.settings.features or \
			"--fetchonly" in self.myopts or \
			"--fetch-all-uri" in self.myopts:
			return os.EX_OK

		shown_verifying_msg = False
		quiet_settings = {}
		for myroot, pkgsettings in self.pkgsettings.items():
			quiet_config = portage.config(clone=pkgsettings)
			quiet_config["PORTAGE_QUIET"] = "1"
			quiet_config.backup_changes("PORTAGE_QUIET")
			quiet_settings[myroot] = quiet_config
			del quiet_config

		failures = 0

		for x in self._mergelist:
			if not isinstance(x, Package) or \
				x.type_name != "ebuild":
				continue

			if x.operation == "uninstall":
				continue

			if not shown_verifying_msg:
				shown_verifying_msg = True
				self._status_msg("Verifying ebuild manifests")

			root_config = x.root_config
			portdb = root_config.trees["porttree"].dbapi
			quiet_config = quiet_settings[root_config.root]
			ebuild_path = portdb.findname(x.cpv, myrepo=x.repo)
			if ebuild_path is None:
				raise AssertionError("ebuild not found for '%s'" % x.cpv)
			quiet_config["O"] = os.path.dirname(ebuild_path)
			if not digestcheck([], quiet_config, strict=True):
				failures |= 1

		if failures:
			return FAILURE
		return os.EX_OK

	def _add_prefetchers(self):

		if not self._parallel_fetch:
			return

		if self._parallel_fetch:

			prefetchers = self._prefetchers

			for pkg in self._mergelist:
				# mergelist can contain solved Blocker instances
				if not isinstance(pkg, Package) or pkg.operation == "uninstall":
					continue
				prefetcher = self._create_prefetcher(pkg)
				if prefetcher is not None:
					# This will start the first prefetcher immediately, so that
					# self._task() won't discard it. This avoids a case where
					# the first prefetcher is discarded, causing the second
					# prefetcher to occupy the fetch queue before the first
					# fetcher has an opportunity to execute.
					prefetchers[pkg] = prefetcher
					self._task_queues.fetch.add(prefetcher)

	def _create_prefetcher(self, pkg):
		"""
		@return: a prefetcher, or None if not applicable
		"""
		prefetcher = None

		if not isinstance(pkg, Package):
			pass

		elif pkg.type_name == "ebuild":

			prefetcher = EbuildFetcher(background=True,
				config_pool=self._ConfigPool(pkg.root,
				self._allocate_config, self._deallocate_config),
				fetchonly=1, fetchall=self._build_opts.fetch_all_uri,
				logfile=self._fetch_log,
				pkg=pkg, prefetch=True, scheduler=self._sched_iface)

		elif pkg.type_name == "binary" and \
			"--getbinpkg" in self.myopts and \
			pkg.root_config.trees["bintree"].isremote(pkg.cpv):

			prefetcher = BinpkgPrefetcher(background=True,
				pkg=pkg, scheduler=self._sched_iface)

		return prefetcher

	async def _run_pkg_pretend(self, loop=None):
		"""
		Since pkg_pretend output may be important, this method sends all
		output directly to stdout (regardless of options like --quiet or
		--jobs).
		"""

		failures = 0
		sched_iface = loop = asyncio._wrap_loop(loop or self._sched_iface)

		for x in self._mergelist:
			if not isinstance(x, Package):
				continue

			if x.operation == "uninstall":
				continue

			if x.eapi in ("0", "1", "2", "3"):
				continue

			if "pretend" not in x.defined_phases:
				continue

			self._termination_check()
			if self._terminated_tasks:
				raise asyncio.CancelledError

			out_str = "Running pre-merge checks for " + colorize("INFORM", x.cpv)
			self._status_msg(out_str)

			root_config = x.root_config
			settings = self._allocate_config(root_config.root)
			settings.setcpv(x)
			if not x.built:
				# Get required SRC_URI metadata (it's not cached in x.metadata
				# because some packages have an extremely large SRC_URI value).
				portdb = root_config.trees["porttree"].dbapi
				(settings.configdict["pkg"]["SRC_URI"],) = await portdb.async_aux_get(
					x.cpv, ["SRC_URI"], myrepo=x.repo, loop=loop
				)

			# setcpv/package.env allows for per-package PORTAGE_TMPDIR so we
			# have to validate it for each package
			rval = _check_temp_dir(settings)
			if rval != os.EX_OK:
				failures += 1
				self._record_pkg_failure(x, settings, FAILURE)
				self._deallocate_config(settings)
				continue

			build_dir_path = os.path.join(
				os.path.realpath(settings["PORTAGE_TMPDIR"]),
				"portage", x.category, x.pf)
			existing_builddir = os.path.isdir(build_dir_path)
			settings["PORTAGE_BUILDDIR"] = build_dir_path
			build_dir = EbuildBuildDir(scheduler=sched_iface,
				settings=settings)
			await build_dir.async_lock()
			current_task = None

			try:

				# Clean up the existing build dir, in case pkg_pretend
				# checks for available space (bug #390711).
				if existing_builddir:
					if x.built:
						tree = "bintree"
						infloc = os.path.join(build_dir_path, "build-info")
						ebuild_path = os.path.join(infloc, x.pf + ".ebuild")
					else:
						tree = "porttree"
						portdb = root_config.trees["porttree"].dbapi
						ebuild_path = portdb.findname(x.cpv, myrepo=x.repo)
						if ebuild_path is None:
							raise AssertionError(
								"ebuild not found for '%s'" % x.cpv)
					portage.package.ebuild.doebuild.doebuild_environment(
						ebuild_path, "clean", settings=settings,
						db=self.trees[settings['EROOT']][tree].dbapi)
					clean_phase = EbuildPhase(background=False,
						phase='clean', scheduler=sched_iface, settings=settings)
					current_task = clean_phase
					clean_phase.start()
					await clean_phase.async_wait()

				if x.built:
					tree = "bintree"
					bintree = root_config.trees["bintree"].dbapi.bintree
					fetched = False

					# Display fetch on stdout, so that it's always clear what
					# is consuming time here.
					if bintree.isremote(x.cpv):
						fetcher = self._get_prefetcher(x)
						if fetcher is None:
							fetcher = BinpkgFetcher(pkg=x, scheduler=loop)
							fetcher.start()
							# We only set the fetched value when fetcher
							# is a BinpkgFetcher, since BinpkgPrefetcher
							# handles fetch, verification, and the
							# bintree.inject call which moves the file.
							fetched = fetcher.pkg_path
						if await fetcher.async_wait() != os.EX_OK:
							failures += 1
							self._record_pkg_failure(x, settings, fetcher.returncode)
							continue

					if fetched is False:
						filename = bintree.getname(x.cpv)
					else:
						filename = fetched
					verifier = BinpkgVerifier(pkg=x,
						scheduler=sched_iface, _pkg_path=filename)
					current_task = verifier
					verifier.start()
					if await verifier.async_wait() != os.EX_OK:
						failures += 1
						self._record_pkg_failure(x, settings, verifier.returncode)
						continue

					if fetched:
						bintree.inject(x.cpv, filename=fetched)

					infloc = os.path.join(build_dir_path, "build-info")
					ensure_dirs(infloc)
					await bintree.dbapi.unpack_metadata(settings, infloc, loop=loop)
					ebuild_path = os.path.join(infloc, x.pf + ".ebuild")
					settings.configdict["pkg"]["EMERGE_FROM"] = "binary"
					settings.configdict["pkg"]["MERGE_TYPE"] = "binary"

				else:
					tree = "porttree"
					portdb = root_config.trees["porttree"].dbapi
					ebuild_path = portdb.findname(x.cpv, myrepo=x.repo)
					if ebuild_path is None:
						raise AssertionError("ebuild not found for '%s'" % x.cpv)
					settings.configdict["pkg"]["EMERGE_FROM"] = "ebuild"
					if self._build_opts.buildpkgonly:
						settings.configdict["pkg"]["MERGE_TYPE"] = "buildonly"
					else:
						settings.configdict["pkg"]["MERGE_TYPE"] = "source"

				portage.package.ebuild.doebuild.doebuild_environment(ebuild_path,
					"pretend", settings=settings,
					db=self.trees[settings['EROOT']][tree].dbapi)

				prepare_build_dirs(root_config.root, settings, cleanup=0)

				vardb = root_config.trees['vartree'].dbapi
				settings["REPLACING_VERSIONS"] = " ".join(
					set(portage.versions.cpv_getversion(match) \
						for match in vardb.match(x.slot_atom) + \
						vardb.match('='+x.cpv)))
				pretend_phase = EbuildPhase(
					phase="pretend", scheduler=sched_iface,
					settings=settings)

				current_task = pretend_phase
				pretend_phase.start()
				ret = await pretend_phase.async_wait()
				if ret != os.EX_OK:
					failures += 1
					self._record_pkg_failure(x, settings, ret)
				portage.elog.elog_process(x.cpv, settings)
			finally:

				if current_task is not None:
					if current_task.isAlive():
						current_task.cancel()
					if current_task.returncode == os.EX_OK:
						clean_phase = EbuildPhase(background=False,
							phase='clean', scheduler=sched_iface,
							settings=settings)
						clean_phase.start()
						await clean_phase.async_wait()

				await build_dir.async_unlock()
				self._deallocate_config(settings)

		if failures:
			return FAILURE
		return os.EX_OK

	def _record_pkg_failure(self, pkg, settings, ret):
		"""Record a package failure. This eliminates the package
		from the --keep-going merge list, and immediately calls
		_failed_pkg_msg if we have not been terminated."""
		self._failed_pkgs.append(
			self._failed_pkg(
				build_dir=settings.get("PORTAGE_BUILDDIR"),
				build_log=settings.get("PORTAGE_LOG_FILE"),
				pkg=pkg,
				returncode=ret,
			)
		)
		if not self._terminated_tasks:
			self._failed_pkg_msg(self._failed_pkgs[-1], "emerge", "for")
			self._status_display.failed = len(self._failed_pkgs)

	def merge(self):
		if "--resume" in self.myopts:
			# We're resuming.
			portage.writemsg_stdout(
				colorize("GOOD", "*** Resuming merge...\n"), noiselevel=-1)
			self._logger.log(" *** Resuming merge...")

		self._save_resume_list()

		try:
			self._background = self._background_mode()
		except self._unknown_internal_error:
			return FAILURE

		rval = self._handle_self_update()
		if rval != os.EX_OK:
			return rval

		for root in self.trees:
			root_config = self.trees[root]["root_config"]

			# Even for --pretend --fetch mode, PORTAGE_TMPDIR is required
			# since it might spawn pkg_nofetch which requires PORTAGE_BUILDDIR
			# for ensuring sane $PWD (bug #239560) and storing elog messages.
			tmpdir = root_config.settings.get("PORTAGE_TMPDIR", "")
			if not tmpdir or not os.path.isdir(tmpdir):
				msg = (
					'The directory specified in your PORTAGE_TMPDIR variable does not exist:',
					tmpdir,
					'Please create this directory or correct your PORTAGE_TMPDIR setting.',
				)
				out = portage.output.EOutput()
				for l in msg:
					out.eerror(l)
				return FAILURE

			if self._background:
				root_config.settings.unlock()
				root_config.settings["PORTAGE_BACKGROUND"] = "1"
				root_config.settings.backup_changes("PORTAGE_BACKGROUND")
				root_config.settings.lock()

			self.pkgsettings[root] = portage.config(
				clone=root_config.settings)

		keep_going = "--keep-going" in self.myopts
		fetchonly = self._build_opts.fetchonly
		mtimedb = self._mtimedb
		failed_pkgs = self._failed_pkgs

		rval = self._generate_digests()
		if rval != os.EX_OK:
			return rval

		# TODO: Immediately recalculate deps here if --keep-going
		#       is enabled and corrupt manifests are detected.
		rval = self._check_manifests()
		if rval != os.EX_OK and not keep_going:
			return rval

		while True:

			received_signal = []

			def sighandler(signum, frame):
				signal.signal(signal.SIGINT, signal.SIG_IGN)
				signal.signal(signal.SIGTERM, signal.SIG_IGN)
				portage.util.writemsg("\n\nExiting on signal %(signal)s\n" % \
					{"signal":signum})
				self.terminate()
				received_signal.append(128 + signum)

			earlier_sigint_handler = signal.signal(signal.SIGINT, sighandler)
			earlier_sigterm_handler = signal.signal(signal.SIGTERM, sighandler)
			earlier_sigcont_handler = \
				signal.signal(signal.SIGCONT, self._sigcont_handler)
			signal.siginterrupt(signal.SIGCONT, False)

			try:
				rval = self._merge()
			finally:
				# Restore previous handlers
				if earlier_sigint_handler is not None:
					signal.signal(signal.SIGINT, earlier_sigint_handler)
				else:
					signal.signal(signal.SIGINT, signal.SIG_DFL)
				if earlier_sigterm_handler is not None:
					signal.signal(signal.SIGTERM, earlier_sigterm_handler)
				else:
					signal.signal(signal.SIGTERM, signal.SIG_DFL)
				if earlier_sigcont_handler is not None:
					signal.signal(signal.SIGCONT, earlier_sigcont_handler)
				else:
					signal.signal(signal.SIGCONT, signal.SIG_DFL)

			self._termination_check()
			if received_signal:
				sys.exit(received_signal[0])

			if rval == os.EX_OK or fetchonly or not keep_going:
				break
			if "resume" not in mtimedb:
				break
			mergelist = self._mtimedb["resume"].get("mergelist")
			if not mergelist:
				break

			if not failed_pkgs:
				break

			for failed_pkg in failed_pkgs:
				mergelist.remove(list(failed_pkg.pkg))

			self._failed_pkgs_all.extend(failed_pkgs)
			del failed_pkgs[:]

			if not mergelist:
				break

			if not self._calc_resume_list():
				break

			clear_caches(self.trees)
			if not self._mergelist:
				break

			self._save_resume_list()
			self._pkg_count.curval = 0
			self._pkg_count.maxval = len([x for x in self._mergelist \
				if isinstance(x, Package) and x.operation == "merge"])
			self._status_display.maxval = self._pkg_count.maxval

		# Cleanup any callbacks that have been registered with the global
		# event loop by calls to the terminate method.
		self._cleanup()

		self._logger.log(" *** Finished. Cleaning up...")

		if failed_pkgs:
			self._failed_pkgs_all.extend(failed_pkgs)
			del failed_pkgs[:]

		printer = portage.output.EOutput()
		background = self._background
		failure_log_shown = False
		if background and len(self._failed_pkgs_all) == 1 and \
			self.myopts.get('--quiet-fail', 'n') != 'y':
			# If only one package failed then just show it's
			# whole log for easy viewing.
			failed_pkg = self._failed_pkgs_all[-1]
			log_file = None
			log_file_real = None

			log_path = self._locate_failure_log(failed_pkg)
			if log_path is not None:
				try:
					log_file = open(_unicode_encode(log_path,
						encoding=_encodings['fs'], errors='strict'), mode='rb')
				except IOError:
					pass
				else:
					if log_path.endswith('.gz'):
						log_file_real = log_file
						log_file =  gzip.GzipFile(filename='',
							mode='rb', fileobj=log_file)

			if log_file is not None:
				try:
					for line in log_file:
						writemsg_level(line, noiselevel=-1)
				except zlib.error as e:
					writemsg_level("%s\n" % (e,), level=logging.ERROR,
						noiselevel=-1)
				finally:
					log_file.close()
					if log_file_real is not None:
						log_file_real.close()
				failure_log_shown = True

		# Dump mod_echo output now since it tends to flood the terminal.
		# This allows us to avoid having more important output, generated
		# later, from being swept away by the mod_echo output.
		mod_echo_output =  _flush_elog_mod_echo()

		if background and not failure_log_shown and \
			self._failed_pkgs_all and \
			self._failed_pkgs_die_msgs and \
			not mod_echo_output:

			for mysettings, key, logentries in self._failed_pkgs_die_msgs:
				root_msg = ""
				if mysettings["ROOT"] != "/":
					root_msg = " merged to %s" % mysettings["ROOT"]
				print()
				printer.einfo("Error messages for package %s%s:" % \
					(colorize("INFORM", key), root_msg))
				print()
				for phase in portage.const.EBUILD_PHASES:
					if phase not in logentries:
						continue
					for msgtype, msgcontent in logentries[phase]:
						if isinstance(msgcontent, str):
							msgcontent = [msgcontent]
						for line in msgcontent:
							printer.eerror(line.strip("\n"))

		if self._post_mod_echo_msgs:
			for msg in self._post_mod_echo_msgs:
				msg()

		if len(self._failed_pkgs_all) > 1 or \
			(self._failed_pkgs_all and keep_going):
			if len(self._failed_pkgs_all) > 1:
				msg = "The following %d packages have " % \
					len(self._failed_pkgs_all) + \
					"failed to build, install, or execute postinst:"
			else:
				msg = "The following package has " + \
					"failed to build, install, or execute postinst:"

			printer.eerror("")
			for line in textwrap.wrap(msg, 72):
				printer.eerror(line)
			printer.eerror("")
			for failed_pkg in self._failed_pkgs_all:
				msg = " %s" % (failed_pkg.pkg,)
				if failed_pkg.postinst_failure:
					msg += " (postinst failed)"
				log_path = self._locate_failure_log(failed_pkg)
				if log_path is not None:
					msg += ", Log file:"
				printer.eerror(msg)
				if log_path is not None:
					printer.eerror("  '%s'" % colorize('INFORM', log_path))
			printer.eerror("")

		if self._failed_pkgs_all:
			return FAILURE
		return os.EX_OK

	def _elog_listener(self, mysettings, key, logentries, fulltext):
		errors = portage.elog.filter_loglevels(logentries, ["ERROR"])
		if errors:
			self._failed_pkgs_die_msgs.append(
				(mysettings, key, errors))

	def _locate_failure_log(self, failed_pkg):

		log_paths = [failed_pkg.build_log]

		for log_path in log_paths:
			if not log_path:
				continue

			try:
				log_size = os.stat(log_path).st_size
			except OSError:
				continue

			if log_size == 0:
				continue

			return log_path

		return None

	def _add_packages(self):
		pkg_queue = self._pkg_queue
		for pkg in self._mergelist:
			if isinstance(pkg, Package):
				pkg_queue.append(pkg)
			elif isinstance(pkg, Blocker):
				pass

	def _system_merge_started(self, merge):
		"""
		Add any unsatisfied runtime deps to self._unsatisfied_system_deps.
		In general, this keeps track of installed system packages with
		unsatisfied RDEPEND or PDEPEND (circular dependencies). It can be
		a fragile situation, so we don't execute any unrelated builds until
		the circular dependencies are built and installed.
		"""
		graph = self._digraph
		if graph is None:
			return
		pkg = merge.merge.pkg

		# Skip this if $ROOT != / since it shouldn't matter if there
		# are unsatisfied system runtime deps in this case.
		if pkg.root_config.settings["ROOT"] != "/":
			return

		completed_tasks = self._completed_tasks
		unsatisfied = self._unsatisfied_system_deps

		def ignore_non_runtime_or_satisfied(priority):
			"""
			Ignore non-runtime and satisfied runtime priorities.
			"""
			if isinstance(priority, DepPriority) and \
				not priority.satisfied and \
				(priority.runtime or priority.runtime_post):
				return False
			return True

		# When checking for unsatisfied runtime deps, only check
		# direct deps since indirect deps are checked when the
		# corresponding parent is merged.
		for child in graph.child_nodes(pkg,
			ignore_priority=ignore_non_runtime_or_satisfied):
			if not isinstance(child, Package) or \
				child.operation == 'uninstall':
				continue
			if child is pkg:
				continue
			if child.operation == 'merge' and \
				child not in completed_tasks:
				unsatisfied.add(child)

	def _merge_wait_exit_handler(self, task):
		self._merge_wait_scheduled.remove(task)
		self._merge_exit(task)

	def _merge_exit(self, merge):
		self._running_tasks.pop(id(merge), None)
		self._do_merge_exit(merge)
		self._deallocate_config(merge.merge.settings)
		if merge.returncode == os.EX_OK and \
			not merge.merge.pkg.installed:
			self._status_display.curval += 1
		self._status_display.merges = len(self._task_queues.merge)
		self._schedule()

	def _do_merge_exit(self, merge):
		pkg = merge.merge.pkg
		if merge.returncode != os.EX_OK:
			settings = merge.merge.settings
			build_dir = settings.get("PORTAGE_BUILDDIR")
			build_log = settings.get("PORTAGE_LOG_FILE")

			self._failed_pkgs.append(self._failed_pkg(
				build_dir=build_dir, build_log=build_log,
				pkg=pkg,
				returncode=merge.returncode))
			if not self._terminated_tasks:
				self._failed_pkg_msg(self._failed_pkgs[-1], "install", "to")
				self._status_display.failed = len(self._failed_pkgs)
			return

		if merge.postinst_failure:
			# Append directly to _failed_pkgs_all for non-critical errors.
			self._failed_pkgs_all.append(self._failed_pkg(
				build_dir=merge.merge.settings.get("PORTAGE_BUILDDIR"),
				build_log=merge.merge.settings.get("PORTAGE_LOG_FILE"),
				pkg=pkg,
				postinst_failure=True,
				returncode=merge.returncode))
			self._failed_pkg_msg(self._failed_pkgs_all[-1],
				"execute postinst for", "for")

		self._task_complete(pkg)
		pkg_to_replace = merge.merge.pkg_to_replace
		if pkg_to_replace is not None:
			# When a package is replaced, mark it's uninstall
			# task complete (if any).
			if self._digraph is not None and \
				pkg_to_replace in self._digraph:
				try:
					self._pkg_queue.remove(pkg_to_replace)
				except ValueError:
					pass
				self._task_complete(pkg_to_replace)
			else:
				self._pkg_cache.pop(pkg_to_replace, None)

		if pkg.installed:
			return

		# Call mtimedb.commit() after each merge so that
		# --resume still works after being interrupted
		# by reboot, sigkill or similar.
		mtimedb = self._mtimedb
		mtimedb["resume"]["mergelist"].remove(list(pkg))
		if not mtimedb["resume"]["mergelist"]:
			del mtimedb["resume"]
		mtimedb.commit()

	def _build_exit(self, build):
		self._running_tasks.pop(id(build), None)
		if build.returncode == os.EX_OK and self._terminated_tasks:
			# We've been interrupted, so we won't
			# add this to the merge queue.
			self.curval += 1
			self._deallocate_config(build.settings)
		elif build.returncode == os.EX_OK:
			self.curval += 1
			merge = PackageMerge(merge=build, scheduler=self._sched_iface)
			self._running_tasks[id(merge)] = merge
			if not build.build_opts.buildpkgonly and \
				build.pkg in self._deep_system_deps:
				# Since dependencies on system packages are frequently
				# unspecified, merge them only when no builds are executing.
				self._merge_wait_queue.append(merge)
				merge.addStartListener(self._system_merge_started)
			else:
				self._task_queues.merge.add(merge)
				merge.addExitListener(self._merge_exit)
				self._status_display.merges = len(self._task_queues.merge)
		else:
			settings = build.settings
			build_dir = settings.get("PORTAGE_BUILDDIR")
			build_log = settings.get("PORTAGE_LOG_FILE")

			self._failed_pkgs.append(self._failed_pkg(
				build_dir=build_dir, build_log=build_log,
				pkg=build.pkg,
				returncode=build.returncode))
			if not self._terminated_tasks:
				self._failed_pkg_msg(self._failed_pkgs[-1], "emerge", "for")
				self._status_display.failed = len(self._failed_pkgs)
			self._deallocate_config(build.settings)
		self._jobs -= 1
		self._status_display.running = self._jobs
		self._schedule()

	def _extract_exit(self, build):
		self._build_exit(build)

	def _task_complete(self, pkg):
		self._completed_tasks.add(pkg)
		self._unsatisfied_system_deps.discard(pkg)
		self._choose_pkg_return_early = False
		blocker_db = self._blocker_db[pkg.root]
		blocker_db.discardBlocker(pkg)

	def _main_loop(self):
		self._main_exit = self._event_loop.create_future()

		if self._max_load is not None and \
			self._loadavg_latency is not None and \
			(self._max_jobs is True or self._max_jobs > 1):
			# We have to schedule periodically, in case the load
			# average has changed since the last call.
			self._main_loadavg_handle = self._event_loop.call_later(
				self._loadavg_latency, self._schedule)

		self._schedule()
		self._event_loop.run_until_complete(self._main_exit)

	def _merge(self):

		if self._opts_no_background.intersection(self.myopts):
			self._set_max_jobs(1)

		failed_pkgs = self._failed_pkgs
		portage.locks._quiet = self._background
		portage.elog.add_listener(self._elog_listener)

		def display_callback():
			self._status_display.display()
			display_callback.handle = self._event_loop.call_later(
				self._max_display_latency, display_callback)
		display_callback.handle = None

		if self._status_display._isatty and not self._status_display.quiet:
			display_callback()
		rval = os.EX_OK

		try:
			self._add_prefetchers()
			if not self._build_opts.fetchonly:
				# Run pkg_pretend concurrently with parallel-fetch, and be careful
				# to respond appropriately to termination, so that we don't start
				# any new tasks after we've been terminated. Temporarily make the
				# status display quiet so that its output is not interleaved with
				# pkg_pretend output.
				status_quiet = self._status_display.quiet
				self._status_display.quiet = True
				try:
					rval = self._sched_iface.run_until_complete(
						self._run_pkg_pretend(loop=self._sched_iface)
					)
				except asyncio.CancelledError:
					self.terminate()
				finally:
					self._status_display.quiet = status_quiet
				self._termination_check()
				if self._terminated_tasks:
					rval = 128 + signal.SIGINT
				if rval != os.EX_OK:
					return rval

			self._add_packages()
			self._main_loop()
		finally:
			self._main_loop_cleanup()
			portage.locks._quiet = False
			portage.elog.remove_listener(self._elog_listener)
			if display_callback.handle is not None:
				display_callback.handle.cancel()
			if failed_pkgs:
				rval = failed_pkgs[-1].returncode

		return rval

	def _main_loop_cleanup(self):
		del self._pkg_queue[:]
		self._completed_tasks.clear()
		self._deep_system_deps.clear()
		self._unsatisfied_system_deps.clear()
		self._choose_pkg_return_early = False
		self._status_display.reset()
		self._digraph = None
		self._task_queues.fetch.clear()
		self._prefetchers.clear()
		self._main_exit = None
		if self._main_loadavg_handle is not None:
			self._main_loadavg_handle.cancel()
			self._main_loadavg_handle = None
		if self._job_delay_timeout_id is not None:
			self._job_delay_timeout_id.cancel()
			self._job_delay_timeout_id = None
		if self._schedule_merge_wakeup_task is not None:
			self._schedule_merge_wakeup_task.cancel()
			self._schedule_merge_wakeup_task = None

	def _choose_pkg(self):
		"""
		Choose a task that has all its dependencies satisfied. This is used
		for parallel build scheduling, and ensures that we don't build
		anything with deep dependencies that have yet to be merged.
		"""

		if self._choose_pkg_return_early:
			return None

		if self._digraph is None:
			if self._is_work_scheduled() and \
				not ("--nodeps" in self.myopts and \
				(self._max_jobs is True or self._max_jobs > 1)):
				self._choose_pkg_return_early = True
				return None
			return self._pkg_queue.pop(0)

		if not self._is_work_scheduled():
			return self._pkg_queue.pop(0)

		self._prune_digraph()

		chosen_pkg = None

		# Prefer uninstall operations when available.
		graph = self._digraph
		for pkg in self._pkg_queue:
			if pkg.operation == 'uninstall' and \
				not graph.child_nodes(pkg):
				chosen_pkg = pkg
				break

		if chosen_pkg is None:
			later = set(self._pkg_queue)
			for pkg in self._pkg_queue:
				later.remove(pkg)
				if not self._dependent_on_scheduled_merges(pkg, later):
					chosen_pkg = pkg
					break

		if chosen_pkg is not None:
			self._pkg_queue.remove(chosen_pkg)

		if chosen_pkg is None:
			# There's no point in searching for a package to
			# choose until at least one of the existing jobs
			# completes.
			self._choose_pkg_return_early = True

		return chosen_pkg

	def _dependent_on_scheduled_merges(self, pkg, later):
		"""
		Traverse the subgraph of the given packages deep dependencies
		to see if it contains any scheduled merges.
		@param pkg: a package to check dependencies for
		@type pkg: Package
		@param later: packages for which dependence should be ignored
			since they will be merged later than pkg anyway and therefore
			delaying the merge of pkg will not result in a more optimal
			merge order
		@type later: set
		@rtype: bool
		@return: True if the package is dependent, False otherwise.
		"""

		graph = self._digraph
		completed_tasks = self._completed_tasks

		dependent = False
		traversed_nodes = set([pkg])
		direct_deps = graph.child_nodes(pkg)
		node_stack = direct_deps
		direct_deps = frozenset(direct_deps)
		while node_stack:
			node = node_stack.pop()
			if node in traversed_nodes:
				continue
			traversed_nodes.add(node)
			if not ((node.installed and node.operation == "nomerge") or \
				(node.operation == "uninstall" and \
				node not in direct_deps) or \
				node in completed_tasks or \
				node in later):
				dependent = True
				break

			# Don't traverse children of uninstall nodes since
			# those aren't dependencies in the usual sense.
			if node.operation != "uninstall":
				node_stack.extend(graph.child_nodes(node))

		return dependent

	def _allocate_config(self, root):
		"""
		Allocate a unique config instance for a task in order
		to prevent interference between parallel tasks.
		"""
		if self._config_pool[root]:
			temp_settings = self._config_pool[root].pop()
		else:
			temp_settings = portage.config(clone=self.pkgsettings[root])
		# Since config.setcpv() isn't guaranteed to call config.reset() due to
		# performance reasons, call it here to make sure all settings from the
		# previous package get flushed out (such as PORTAGE_LOG_FILE).
		temp_settings.reload()
		temp_settings.reset()
		return temp_settings

	def _deallocate_config(self, settings):
		self._config_pool[settings['EROOT']].append(settings)

	def _keep_scheduling(self):
		return bool(not self._terminated.is_set() and self._pkg_queue and \
			not (self._failed_pkgs and not self._build_opts.fetchonly))

	def _is_work_scheduled(self):
		return bool(self._running_tasks)

	def _running_job_count(self):
		return self._jobs

	def _schedule_tasks(self):

		while True:

			state_change = 0

			# When the number of jobs and merges drops to zero,
			# process a single merge from _merge_wait_queue if
			# it's not empty. We only process one since these are
			# special packages and we want to ensure that
			# parallel-install does not cause more than one of
			# them to install at the same time.
			if (self._merge_wait_queue and not self._jobs and
				not self._task_queues.merge):
				task = self._merge_wait_queue.popleft()
				task.scheduler = self._sched_iface
				self._merge_wait_scheduled.append(task)
				self._task_queues.merge.add(task)
				task.addExitListener(self._merge_wait_exit_handler)
				self._status_display.merges = len(self._task_queues.merge)
				state_change += 1

			if self._schedule_tasks_imp():
				state_change += 1

			self._status_display.display()

			# Cancel prefetchers if they're the only reason
			# the main poll loop is still running.
			if self._failed_pkgs and not self._build_opts.fetchonly and \
				not self._is_work_scheduled() and \
				self._task_queues.fetch:
				# Since this happens asynchronously, it doesn't count in
				# state_change (counting it triggers an infinite loop).
				self._task_queues.fetch.clear()

			if not (state_change or \
				(self._merge_wait_queue and not self._jobs and
				not self._task_queues.merge)):
				break

		if not (self._is_work_scheduled() or
			self._keep_scheduling() or self._main_exit.done()):
			self._main_exit.set_result(None)
		elif self._main_loadavg_handle is not None:
			self._main_loadavg_handle.cancel()
			self._main_loadavg_handle = self._event_loop.call_later(
				self._loadavg_latency, self._schedule)

		# Failure to schedule *after* self._task_queues.merge becomes
		# empty will cause the scheduler to hang as in bug 711322.
		# Do not rely on scheduling which occurs via the _merge_exit
		# method, since the order of callback invocation may cause
		# self._task_queues.merge to appear non-empty when it is
		# about to become empty.
		if (self._task_queues.merge and (self._schedule_merge_wakeup_task is None
			or self._schedule_merge_wakeup_task.done())):
			self._schedule_merge_wakeup_task = asyncio.ensure_future(
				self._task_queues.merge.wait(loop=self._event_loop), loop=self._event_loop)
			self._schedule_merge_wakeup_task.add_done_callback(
				self._schedule_merge_wakeup)

	def _schedule_merge_wakeup(self, future):
		if not future.cancelled():
			future.result()
			if self._main_exit is not None and not self._main_exit.done():
				self._schedule()

	def _sigcont_handler(self, signum, frame):
		self._sigcont_time = time.time()

	def _job_delay(self):
		"""
		@rtype: bool
		@return: True if job scheduling should be delayed, False otherwise.
		"""

		if self._jobs and self._max_load is not None:

			current_time = time.time()

			if self._sigcont_time is not None:

				elapsed_seconds = current_time - self._sigcont_time
				# elapsed_seconds < 0 means the system clock has been adjusted
				if elapsed_seconds > 0 and \
					elapsed_seconds < self._sigcont_delay:

					if self._job_delay_timeout_id is not None:
						self._job_delay_timeout_id.cancel()

					self._job_delay_timeout_id = self._event_loop.call_later(
						self._sigcont_delay - elapsed_seconds,
						self._schedule)
					return True

				# Only set this to None after the delay has expired,
				# since this method may be called again before the
				# delay has expired.
				self._sigcont_time = None

			try:
				avg1, avg5, avg15 = getloadavg()
			except OSError:
				return False

			delay = self._job_delay_max * avg1 / self._max_load
			if delay > self._job_delay_max:
				delay = self._job_delay_max
			elapsed_seconds = current_time - self._previous_job_start_time
			# elapsed_seconds < 0 means the system clock has been adjusted
			if elapsed_seconds > 0 and elapsed_seconds < delay:

				if self._job_delay_timeout_id is not None:
					self._job_delay_timeout_id.cancel()

				self._job_delay_timeout_id = self._event_loop.call_later(
					delay - elapsed_seconds, self._schedule)
				return True

		return False

	def _schedule_tasks_imp(self):
		"""
		@rtype: bool
		@return: True if state changed, False otherwise.
		"""

		state_change = 0

		while True:

			if not self._keep_scheduling():
				return bool(state_change)

			if self._choose_pkg_return_early or \
				self._merge_wait_scheduled or \
				(self._jobs and self._unsatisfied_system_deps) or \
				not self._can_add_job() or \
				self._job_delay():
				return bool(state_change)

			pkg = self._choose_pkg()
			if pkg is None:
				return bool(state_change)

			state_change += 1

			if not pkg.installed:
				self._pkg_count.curval += 1

			task = self._task(pkg)

			if pkg.installed:
				merge = PackageMerge(merge=task, scheduler=self._sched_iface)
				self._running_tasks[id(merge)] = merge
				self._task_queues.merge.addFront(merge)
				merge.addExitListener(self._merge_exit)

			elif pkg.built:
				self._jobs += 1
				self._previous_job_start_time = time.time()
				self._status_display.running = self._jobs
				self._running_tasks[id(task)] = task
				task.scheduler = self._sched_iface
				self._task_queues.jobs.add(task)
				task.addExitListener(self._extract_exit)

			else:
				self._jobs += 1
				self._previous_job_start_time = time.time()
				self._status_display.running = self._jobs
				self._running_tasks[id(task)] = task
				task.scheduler = self._sched_iface
				self._task_queues.jobs.add(task)
				task.addExitListener(self._build_exit)

		return bool(state_change)

	def _get_prefetcher(self, pkg):
		try:
			prefetcher = self._prefetchers.pop(pkg, None)
		except KeyError:
			# KeyError observed with PyPy 1.8, despite None given as default.
			# Note that PyPy 1.8 has the same WeakValueDictionary code as
			# CPython 2.7, so it may be possible for CPython to raise KeyError
			# here as well.
			prefetcher = None
		if prefetcher is not None and not prefetcher.isAlive():
			try:
				self._task_queues.fetch._task_queue.remove(prefetcher)
			except ValueError:
				pass
			prefetcher = None
		return prefetcher

	def _task(self, pkg):

		pkg_to_replace = None
		if pkg.operation != "uninstall":
			vardb = pkg.root_config.trees["vartree"].dbapi
			previous_cpv = [x for x in vardb.match(pkg.slot_atom) \
				if portage.cpv_getkey(x) == pkg.cp]
			if not previous_cpv and vardb.cpv_exists(pkg.cpv):
				# same cpv, different SLOT
				previous_cpv = [pkg.cpv]
			if previous_cpv:
				previous_cpv = previous_cpv.pop()
				pkg_to_replace = self._pkg(previous_cpv,
					"installed", pkg.root_config, installed=True,
					operation="uninstall")

		prefetcher = self._get_prefetcher(pkg)

		task = MergeListItem(args_set=self._args_set,
			background=self._background, binpkg_opts=self._binpkg_opts,
			build_opts=self._build_opts,
			config_pool=self._ConfigPool(pkg.root,
			self._allocate_config, self._deallocate_config),
			emerge_opts=self.myopts,
			find_blockers=self._find_blockers(pkg), logger=self._logger,
			mtimedb=self._mtimedb, pkg=pkg, pkg_count=self._pkg_count.copy(),
			pkg_to_replace=pkg_to_replace,
			prefetcher=prefetcher,
			scheduler=self._sched_iface,
			settings=self._allocate_config(pkg.root),
			statusMessage=self._status_msg,
			world_atom=self._world_atom)

		return task

	def _failed_pkg_msg(self, failed_pkg, action, preposition):
		pkg = failed_pkg.pkg
		msg = "%s to %s %s" % \
			(bad("Failed"), action, colorize("INFORM", pkg.cpv))
		if pkg.root_config.settings["ROOT"] != "/":
			msg += " %s %s" % (preposition, pkg.root)

		log_path = self._locate_failure_log(failed_pkg)
		if log_path is not None:
			msg += ", Log file:"
		self._status_msg(msg)

		if log_path is not None:
			self._status_msg(" '%s'" % (colorize("INFORM", log_path),))

	def _status_msg(self, msg):
		"""
		Display a brief status message (no newlines) in the status display.
		This is called by tasks to provide feedback to the user. This
		delegates the resposibility of generating \r and \n control characters,
		to guarantee that lines are created or erased when necessary and
		appropriate.

		@type msg: str
		@param msg: a brief status message (no newlines allowed)
		"""
		if not self._background:
			writemsg_level("\n")
		self._status_display.displayMessage(msg)

	def _save_resume_list(self):
		"""
		Do this before verifying the ebuild Manifests since it might
		be possible for the user to use --resume --skipfirst get past
		a non-essential package with a broken digest.
		"""
		mtimedb = self._mtimedb

		mtimedb["resume"] = {}
		# Stored as a dict starting with portage-2.1.6_rc1, and supported
		# by >=portage-2.1.3_rc8. Versions <portage-2.1.3_rc8 only support
		# a list type for options.
		mtimedb["resume"]["myopts"] = self.myopts.copy()

		# Convert Atom instances to plain str.
		mtimedb["resume"]["favorites"] = [str(x) for x in self._favorites]
		mtimedb["resume"]["mergelist"] = [list(x) \
			for x in self._mergelist \
			if isinstance(x, Package) and x.operation == "merge"]

		mtimedb.commit()

	def _calc_resume_list(self):
		"""
		Use the current resume list to calculate a new one,
		dropping any packages with unsatisfied deps.
		@rtype: bool
		@return: True if successful, False otherwise.
		"""
		print(colorize("GOOD", "*** Resuming merge..."))

		# free some memory before creating
		# the resume depgraph
		self._destroy_graph()

		myparams = create_depgraph_params(self.myopts, None)
		success = False
		e = None
		try:
			success, mydepgraph, dropped_tasks = resume_depgraph(
				self.settings, self.trees, self._mtimedb, self.myopts,
				myparams, self._spinner)
		except depgraph.UnsatisfiedResumeDep as exc:
			# rename variable to avoid python-3.0 error:
			# SyntaxError: can not delete variable 'e' referenced in nested
			#              scope
			e = exc
			mydepgraph = e.depgraph
			dropped_tasks = {}

		if e is not None:
			def unsatisfied_resume_dep_msg():
				mydepgraph.display_problems()
				out = portage.output.EOutput()
				out.eerror("One or more packages are either masked or " + \
					"have missing dependencies:")
				out.eerror("")
				indent = "  "
				show_parents = set()
				for dep in e.value:
					if dep.parent in show_parents:
						continue
					show_parents.add(dep.parent)
					if dep.atom is None:
						out.eerror(indent + "Masked package:")
						out.eerror(2 * indent + str(dep.parent))
						out.eerror("")
					else:
						out.eerror(indent + str(dep.atom) + " pulled in by:")
						out.eerror(2 * indent + str(dep.parent))
						out.eerror("")
				msg = "The resume list contains packages " + \
					"that are either masked or have " + \
					"unsatisfied dependencies. " + \
					"Please restart/continue " + \
					"the operation manually, or use --skipfirst " + \
					"to skip the first package in the list and " + \
					"any other packages that may be " + \
					"masked or have missing dependencies."
				for line in textwrap.wrap(msg, 72):
					out.eerror(line)
			self._post_mod_echo_msgs.append(unsatisfied_resume_dep_msg)
			return False

		if success and self._show_list():
			mydepgraph.display(mydepgraph.altlist(), favorites=self._favorites)

		if not success:
			self._post_mod_echo_msgs.append(mydepgraph.display_problems)
			return False
		mydepgraph.display_problems()
		self._init_graph(mydepgraph.schedulerGraph())

		msg_width = 75
		for task, atoms in dropped_tasks.items():
			if not (isinstance(task, Package) and task.operation == "merge"):
				continue
			pkg = task
			msg = "emerge --keep-going:" + \
				" %s" % (pkg.cpv,)
			if pkg.root_config.settings["ROOT"] != "/":
				msg += " for %s" % (pkg.root,)
			if not atoms:
				msg += " dropped because it is masked or unavailable"
			else:
				msg += " dropped because it requires %s" % ", ".join(atoms)
			for line in textwrap.wrap(msg, msg_width):
				eerror(line, phase="other", key=pkg.cpv)
			settings = self.pkgsettings[pkg.root]
			# Ensure that log collection from $T is disabled inside
			# elog_process(), since any logs that might exist are
			# not valid here.
			settings.pop("T", None)
			portage.elog.elog_process(pkg.cpv, settings)
			self._failed_pkgs_all.append(self._failed_pkg(pkg=pkg))

		return True

	def _show_list(self):
		myopts = self.myopts
		if "--quiet" not in myopts and \
			("--ask" in myopts or "--tree" in myopts or \
			"--verbose" in myopts):
			return True
		return False

	def _world_atom(self, pkg):
		"""
		Add or remove the package to the world file, but only if
		it's supposed to be added or removed. Otherwise, do nothing.
		"""

		if set(("--buildpkgonly", "--fetchonly",
			"--fetch-all-uri",
			"--oneshot", "--onlydeps",
			"--pretend")).intersection(self.myopts):
			return

		if pkg.root != self.target_root:
			return

		args_set = self._args_set
		if not args_set.findAtomForPackage(pkg):
			return

		logger = self._logger
		pkg_count = self._pkg_count
		root_config = pkg.root_config
		world_set = root_config.sets["selected"]
		world_locked = False
		atom = None

		if pkg.operation != "uninstall":
			atom = self._world_atoms.get(pkg)

		try:

			if hasattr(world_set, "lock"):
				world_set.lock()
				world_locked = True

			if hasattr(world_set, "load"):
				world_set.load() # maybe it's changed on disk

			if pkg.operation == "uninstall":
				if hasattr(world_set, "cleanPackage"):
					world_set.cleanPackage(pkg.root_config.trees["vartree"].dbapi,
							pkg.cpv)
				if hasattr(world_set, "remove"):
					for s in pkg.root_config.setconfig.active:
						world_set.remove(SETPREFIX+s)
			else:
				if atom is not None:
					if hasattr(world_set, "add"):
						self._status_msg(('Recording %s in "world" ' + \
							'favorites file...') % atom)
						logger.log(" === (%s of %s) Updating world file (%s)" % \
							(pkg_count.curval, pkg_count.maxval, pkg.cpv))
						world_set.add(atom)
					else:
						writemsg_level('\n!!! Unable to record %s in "world"\n' % \
							(atom,), level=logging.WARN, noiselevel=-1)
		finally:
			if world_locked:
				world_set.unlock()

	def _pkg(self, cpv, type_name, root_config, installed=False,
		operation=None, myrepo=None):
		"""
		Get a package instance from the cache, or create a new
		one if necessary. Raises KeyError from aux_get if it
		failures for some reason (package does not exist or is
		corrupt).
		"""

		# Reuse existing instance when available.
		pkg = self._pkg_cache.get(Package._gen_hash_key(cpv=cpv,
			type_name=type_name, repo_name=myrepo, root_config=root_config,
			installed=installed, operation=operation))

		if pkg is not None:
			return pkg

		tree_type = depgraph.pkg_tree_map[type_name]
		db = root_config.trees[tree_type].dbapi
		db_keys = list(self.trees[root_config.root][
			tree_type].dbapi._aux_cache_keys)
		metadata = zip(db_keys, db.aux_get(cpv, db_keys, myrepo=myrepo))
		pkg = Package(built=(type_name != "ebuild"),
			cpv=cpv, installed=installed, metadata=metadata,
			root_config=root_config, type_name=type_name)
		self._pkg_cache[pkg] = pkg
		return pkg
