# -*- coding:utf-8 -*-


import copy
import functools
import os
import types
from pprint import pformat

from _emerge.Package import Package

# import our initialized portage instance
from repoman._portage import portage
from repoman.modules.scan.scanbase import ScanBase
from repoman.modules.scan.depend._depend_checks import _depend_checks
from repoman.modules.scan.depend._gen_arches import _gen_arches
from portage.dep import Atom
from portage.package.ebuild.profile_iuse import iter_iuse_vars
from portage.util import getconfig
from portage.util.futures import asyncio
from portage.util.futures.executor.fork import ForkExecutor
from portage.util.futures.iter_completed import async_iter_completed


def sort_key(item):
	return item[2].sub_path


class ProfileDependsChecks(ScanBase):
	'''Perform dependency checks for the different profiles'''

	def __init__(self, **kwargs):
		'''Class init

		@param qatracker: QATracker instance
		@param portdb: portdb instance
		@param profiles: dictionary
		@param options: cli options
		@param repo_settings: repository settings instance
		@param include_arches: set
		@param include_profiles: set
		@param caches: dictionary of our caches
		@param repoman_incrementals: tuple
		@param env: the environment
		@param have: dictionary instance
		@param dev_keywords: developer profile keywords
		@param repo_metadata: dictionary of various repository items.
		'''
		self.qatracker = kwargs.get('qatracker')
		self.portdb = kwargs.get('portdb')
		self.profiles = kwargs.get('profiles')
		self.options = kwargs.get('options')
		self.repo_settings = kwargs.get('repo_settings')
		self.include_arches = kwargs.get('include_arches')
		self.include_profiles = kwargs.get('include_profiles')
		self.caches = kwargs.get('caches')
		self.repoman_incrementals = kwargs.get('repoman_incrementals')
		self.env = kwargs.get('env')
		self.have = kwargs.get('have')
		self.dev_keywords = kwargs.get('dev_keywords')
		self.repo_metadata = kwargs.get('repo_metadata')

	def check(self, **kwargs):
		'''Perform profile dependant dependency checks

		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		@returns: dictionary
		'''
		ebuild = kwargs.get('ebuild').get()
		pkg = kwargs.get('pkg').get()

		ebuild.unknown_pkgs, ebuild.baddepsyntax = _depend_checks(
			ebuild, pkg, self.portdb, self.qatracker, self.repo_metadata,
			self.repo_settings.qadata)

		relevant_profiles = []
		for keyword, arch, groups in _gen_arches(ebuild, self.options,
			self.repo_settings, self.profiles):
			if arch not in self.profiles:
				# A missing profile will create an error further down
				# during the KEYWORDS verification.
				continue

			if self.include_arches is not None:
				if arch not in self.include_arches:
					continue

			for prof in self.profiles[arch]:
				if self.include_profiles is not None:
					if prof.sub_path not in self.include_profiles:
						continue
				relevant_profiles.append((keyword, groups, prof))

		relevant_profiles.sort(key=sort_key)
		ebuild.relevant_profiles = relevant_profiles

		if self.options.jobs <= 1:
			for task in self._iter_tasks(None, None, ebuild, pkg):
				task, results = task
				for result in results:
					self._check_result(task, result)

		loop = asyncio.get_event_loop()
		loop.run_until_complete(self._async_check(loop, **kwargs))

		return False

	async def _async_check(self, loop, **kwargs):
		'''Perform async profile dependant dependency checks

		@param arches:
		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		@param baddepsyntax: boolean
		@param unknown_pkgs: set of tuples (type, atom.unevaluated_atom)
		@returns: dictionary
		'''
		ebuild = kwargs.get('ebuild').get()
		pkg = kwargs.get('pkg').get()
		unknown_pkgs = ebuild.unknown_pkgs
		baddepsyntax = ebuild.baddepsyntax

		# Use max_workers=True to ensure immediate fork, since _iter_tasks
		# needs the fork to create a snapshot of current state.
		executor = ForkExecutor(max_workers=self.options.jobs)

		if self.options.jobs > 1:
			for future_done_set in async_iter_completed(self._iter_tasks(loop, executor, ebuild, pkg),
				max_jobs=self.options.jobs, max_load=self.options.load_average):
				for task in (await future_done_set):
					task, results = task.result()
					for result in results:
						self._check_result(task, result)

		if not baddepsyntax and unknown_pkgs:
			type_map = {}
			for mytype, atom in unknown_pkgs:
				type_map.setdefault(mytype, set()).add(atom)
			for mytype, atoms in type_map.items():
				self.qatracker.add_error(
					"dependency.unknown", "%s: %s: %s"
					% (ebuild.relative_path, mytype, ", ".join(sorted(atoms))))

	async def _task(self, task):
		await task.future
		return (task, task.future.result())

	def _iter_tasks(self, loop, executor, ebuild, pkg):
		for keyword, groups, prof in ebuild.relevant_profiles:

			is_stable_profile = prof.status == "stable"
			is_dev_profile = prof.status == "dev" and \
				self.options.include_dev
			is_exp_profile = prof.status == "exp" and \
				self.options.include_exp_profiles == 'y'
			if not (is_stable_profile or is_dev_profile or is_exp_profile):
				continue

			dep_settings = self.caches['arch'].get(prof.sub_path)
			if dep_settings is None:
				dep_settings = portage.config(
					config_profile_path=prof.abs_path,
					config_incrementals=self.repoman_incrementals,
					config_root=self.repo_settings.config_root,
					local_config=False,
					_unmatched_removal=self.options.unmatched_removal,
					env=self.env, repositories=self.repo_settings.repoman_settings.repositories)

				if not prof.abs_path:
					self._populate_implicit_iuse(dep_settings,
						self.repo_settings.repo_config.eclass_db.porttrees)

				dep_settings.categories = self.repo_settings.repoman_settings.categories
				if self.options.without_mask:
					dep_settings._mask_manager_obj = \
						copy.deepcopy(dep_settings._mask_manager)
					dep_settings._mask_manager._pmaskdict.clear()
				self.caches['arch'][prof.sub_path] = dep_settings

			xmatch_cache_key = (prof.sub_path, tuple(groups))
			xcache = self.caches['arch_xmatch'].get(xmatch_cache_key)
			if xcache is None:
				self.portdb.melt()
				self.portdb.freeze()
				xcache = self.portdb.xcache
				xcache.update(self.caches['shared_xmatch'])
				self.caches['arch_xmatch'][xmatch_cache_key] = xcache

			self.repo_settings.trees[self.repo_settings.root]["porttree"].settings = dep_settings
			self.portdb.settings = dep_settings
			self.portdb.xcache = xcache

			dep_settings["ACCEPT_KEYWORDS"] = " ".join(groups)
			# just in case, prevent config.reset() from nuking these.
			dep_settings.backup_changes("ACCEPT_KEYWORDS")

			# This attribute is used in dbapi._match_use() to apply
			# use.stable.{mask,force} settings based on the stable
			# status of the parent package. This is required in order
			# for USE deps of unstable packages to be resolved correctly,
			# since otherwise use.stable.{mask,force} settings of
			# dependencies may conflict (see bug #456342).
			dep_settings._parent_stable = dep_settings._isStable(pkg)

			# Handle package.use*.{force,mask) calculation, for use
			# in dep_check.
			dep_settings.useforce = dep_settings._use_manager.getUseForce(
				pkg, stable=dep_settings._parent_stable)
			dep_settings.usemask = dep_settings._use_manager.getUseMask(
				pkg, stable=dep_settings._parent_stable)

			task = types.SimpleNamespace(ebuild=ebuild, prof=prof, keyword=keyword)

			target = functools.partial(self._task_subprocess, task, pkg, dep_settings)

			if self.options.jobs <= 1:
				yield (task, target())
			else:
				task.future = asyncio.ensure_future(loop.run_in_executor(executor, target), loop=loop)
				yield asyncio.ensure_future(self._task(task), loop=loop)


	def _task_subprocess(self, task, pkg, dep_settings):
			ebuild = task.ebuild
			baddepsyntax = ebuild.baddepsyntax
			results = []
			prof = task.prof
			if not baddepsyntax:
				ismasked = not ebuild.archs or \
					pkg.cpv not in self.portdb.xmatch("match-visible",
					Atom("%s::%s" % (pkg.cp, self.repo_settings.repo_config.name)))
				if ismasked:
					if not self.have['pmasked']:
						self.have['pmasked'] = bool(dep_settings._getMaskAtom(
							pkg.cpv, ebuild.metadata))
					if self.options.ignore_masked:
						return results
					# we are testing deps for a masked package; give it some lee-way
					suffix = "masked"
					matchmode = "minimum-all-ignore-profile"
				else:
					suffix = ""
					matchmode = "minimum-visible"

				if not self.have['dev_keywords']:
					self.have['dev_keywords'] = \
						bool(self.dev_keywords.intersection(ebuild.keywords))

				if prof.status == "dev":
					suffix = suffix + "indev"
				elif prof.status == "exp":
					suffix = suffix + "inexp"

				for mytype in Package._dep_keys:

					mykey = "dependency.bad" + suffix
					myvalue = ebuild.metadata[mytype]
					if not myvalue:
						continue

					success, atoms = portage.dep_check(
						myvalue, self.portdb, dep_settings,
						use="all", mode=matchmode, trees=self.repo_settings.trees)

					results.append(types.SimpleNamespace(atoms=atoms, success=success, mykey=mykey, mytype=mytype))

			return results


	def _check_result(self, task, result):
					prof = task.prof
					keyword = task.keyword
					ebuild = task.ebuild
					unknown_pkgs = ebuild.unknown_pkgs

					success = result.success
					atoms = result.atoms
					mykey = result.mykey
					mytype = result.mytype

					if success:
						if atoms:

							# Don't bother with dependency.unknown for
							# cases in which *DEPEND.bad is triggered.
							for atom in atoms:
								# dep_check returns all blockers and they
								# aren't counted for *DEPEND.bad, so we
								# ignore them here.
								if not atom.blocker:
									unknown_pkgs.discard(
										(mytype, atom.unevaluated_atom))

							if not prof.sub_path:
								# old-style virtuals currently aren't
								# resolvable with empty profile, since
								# 'virtuals' mappings are unavailable
								# (it would be expensive to search
								# for PROVIDE in all ebuilds)
								atoms = [
									atom for atom in atoms if not (
										atom.cp.startswith('virtual/')
										and not self.portdb.cp_list(atom.cp))]

							# we have some unsolvable deps
							# remove ! deps, which always show up as unsatisfiable
							all_atoms = [
								str(atom.unevaluated_atom)
								for atom in atoms if not atom.blocker]

							# if we emptied out our list, continue:
							if not all_atoms:
								return

							# Filter out duplicates.  We do this by hand (rather
							# than use a set) so the order is stable and better
							# matches the order that's in the ebuild itself.
							atoms = []
							for atom in all_atoms:
								if atom not in atoms:
									atoms.append(atom)

							if self.options.output_style in ['column']:
								self.qatracker.add_error(mykey,
									"%s: %s: %s(%s) %s"
									% (ebuild.relative_path, mytype, keyword,
										prof, repr(atoms)))
							else:
								self.qatracker.add_error(mykey,
									"%s: %s: %s(%s)\n%s"
									% (ebuild.relative_path, mytype, keyword,
										prof, pformat(atoms, indent=6)))
					else:
						if self.options.output_style in ['column']:
							self.qatracker.add_error(mykey,
								"%s: %s: %s(%s) %s"
								% (ebuild.relative_path, mytype, keyword,
									prof, repr(atoms)))
						else:
							self.qatracker.add_error(mykey,
								"%s: %s: %s(%s)\n%s"
								% (ebuild.relative_path, mytype, keyword,
									prof, pformat(atoms, indent=6)))

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check])

	@staticmethod
	def _populate_implicit_iuse(config, repo_locations):
		"""
		Populate implicit IUSE for the empty profile, see bug 660982.

		@param config: config instance for the empty profile
		@type config: portage.config
		@param repo_locations: locations of repositories containing relevant
			implicit IUSE settings
		@type repo_locations: list
		"""
		dest = config.configdict['defaults']
		for location in repo_locations:
			for parent_dir, dirs, files in os.walk(os.path.join(location, 'profiles')):
				src = getconfig(os.path.join(parent_dir, 'make.defaults'))
				if not src:
					continue
				for k, v in iter_iuse_vars(src):
					v_before = dest.get(k)
					if v_before is not None:
						merged_values = set(v_before.split())
						merged_values.update(v.split())
						v = ' '.join(sorted(merged_values))
					dest[k] = v

		config.regenerate()
		config._init_iuse()
