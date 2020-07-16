# -*- coding:utf-8 -*-

from __future__ import print_function

import logging
from itertools import chain

import portage
from portage import normalize_path
from portage import os
from portage._sets.base import InternalPackageSet
from portage.output import green
from portage.util.futures.extendedfutures import ExtendedFuture
from repoman.metadata import get_metadata_xsd
from repoman.modules.commit import repochecks
from repoman.modules.commit import manifest
from repoman.profile import check_profiles, dev_profile_keywords, setup_profile
from repoman.repos import repo_metadata
from repoman.modules.scan.module import ModuleConfig
from repoman.modules.scan.scan import scan
from repoman.modules.vcs.vcs import vcs_files_to_cps


DATA_TYPES = {'dict': dict, 'Future': ExtendedFuture, 'list': list, 'set': set}


class Scanner(object):
	'''Primary scan class.  Operates all the small Q/A tests and checks'''

	def __init__(self, repo_settings, myreporoot, config_root, options,
				vcs_settings, mydir, env):
		'''Class __init__'''
		self.repo_settings = repo_settings
		self.config_root = config_root
		self.options = options
		self.vcs_settings = vcs_settings
		self.env = env

		# Repoman sets it's own ACCEPT_KEYWORDS and we don't want it to
		# behave incrementally.
		self.repoman_incrementals = tuple(
			x for x in portage.const.INCREMENTALS if x != 'ACCEPT_KEYWORDS')

		self.categories = []
		for path in self.repo_settings.repo_config.eclass_db.porttrees:
			self.categories.extend(portage.util.grabfile(
				os.path.join(path, 'profiles', 'categories')))
		self.repo_settings.repoman_settings.categories = frozenset(
			portage.util.stack_lists([self.categories], incremental=1))
		self.categories = self.repo_settings.repoman_settings.categories

		self.portdb = repo_settings.portdb
		self.portdb.settings = self.repo_settings.repoman_settings

		digest_only = self.options.mode != 'manifest-check' \
			and self.options.digest == 'y'
		self.generate_manifest = digest_only or self.options.mode in \
			("manifest", 'commit', 'fix')

		# We really only need to cache the metadata that's necessary for visibility
		# filtering. Anything else can be discarded to reduce memory consumption.
		if not self.generate_manifest:
			# Don't do this when generating manifests, since that uses
			# additional keys if spawn_nofetch is called (RESTRICT and
			# DEFINED_PHASES).
			self.portdb._aux_cache_keys.clear()
			self.portdb._aux_cache_keys.update(
				["EAPI", "IUSE", "KEYWORDS", "repository", "SLOT"])

		self.reposplit = myreporoot.split(os.path.sep)
		self.repolevel = len(self.reposplit)

		if self.options.mode == 'commit':
			repochecks.commit_check(self.repolevel, self.reposplit)
			repochecks.conflict_check(self.vcs_settings, self.options)

		# Make startdir relative to the canonical repodir, so that we can pass
		# it to digestgen and it won't have to be canonicalized again.
		if self.repolevel == 1:
			startdir = self.repo_settings.repodir
		else:
			startdir = normalize_path(mydir)
			startdir = os.path.join(
				self.repo_settings.repodir, *startdir.split(os.sep)[-2 - self.repolevel + 3:])

		# get lists of valid keywords, licenses, and use
		new_data = repo_metadata(self.portdb, self.repo_settings.repoman_settings)
		kwlist, liclist, uselist, profile_list, \
			global_pmaskdict, liclist_deprecated = new_data
		self.repo_metadata = {
			'kwlist': kwlist,
			'liclist': liclist,
			'uselist': uselist,
			'profile_list': profile_list,
			'pmaskdict': global_pmaskdict,
			'lic_deprecated': liclist_deprecated,
			'package.deprecated': InternalPackageSet(initial_atoms=portage.util.stack_lists(
				[portage.util.grabfile_package(os.path.join(path, 'profiles', 'package.deprecated'), recursive=True)
				for path in self.portdb.porttrees], incremental=True))
		}

		self.repo_settings.repoman_settings['PORTAGE_ARCHLIST'] = ' '.join(sorted(kwlist))
		self.repo_settings.repoman_settings.backup_changes('PORTAGE_ARCHLIST')

		profiles = setup_profile(profile_list)

		check_profiles(profiles, self.repo_settings.repoman_settings.archlist())

		scanlist = scan(self.repolevel, self.reposplit, startdir, self.categories, self.repo_settings)

		self.dev_keywords = dev_profile_keywords(profiles)

		self.qatracker = self.vcs_settings.qatracker

		if self.options.echangelog is None and self.repo_settings.repo_config.update_changelog:
			self.options.echangelog = 'y'

		if self.vcs_settings.vcs is None:
			self.options.echangelog = 'n'

		# Initialize the ModuleConfig class here
		# TODO Add layout.conf masters repository.yml config to the list to load/stack
		self.moduleconfig = ModuleConfig(self.repo_settings.masters_list,
										self.repo_settings.repoman_settings.valid_versions,
										repository_modules=self.options.experimental_repository_modules == 'y')

		checks = {}
		# The --echangelog option causes automatic ChangeLog generation,
		# which invalidates changelog.ebuildadded and changelog.missing
		# checks.
		# Note: Some don't use ChangeLogs in distributed SCMs.
		# It will be generated on server side from scm log,
		# before package moves to the rsync server.
		# This is needed because they try to avoid merge collisions.
		# Gentoo's Council decided to always use the ChangeLog file.
		# TODO: shouldn't this just be switched on the repo, iso the VCS?
		is_echangelog_enabled = self.options.echangelog in ('y', 'force')
		self.vcs_settings.vcs_is_cvs_or_svn = self.vcs_settings.vcs in ('cvs', 'svn')
		checks['changelog'] = not is_echangelog_enabled and self.vcs_settings.vcs_is_cvs_or_svn

		if self.options.mode == "manifest" or self.options.quiet:
			pass
		elif self.options.pretend:
			print(green("\nRepoMan does a once-over of the neighborhood..."))
		else:
			print(green("\nRepoMan scours the neighborhood..."))

		self.changed = self.vcs_settings.changes
		# bypass unneeded VCS operations if not needed
		if (self.options.if_modified == "y" or
			self.options.mode not in ("manifest", "manifest-check")):
			self.changed.scan()

		self.have = {
			'pmasked': False,
			'dev_keywords': False,
		}

		# NOTE: match-all caches are not shared due to potential
		# differences between profiles in _get_implicit_iuse.
		self.caches = {
			'arch': {},
			'arch_xmatch': {},
			'shared_xmatch': {"cp-list": {}},
		}

		self.include_arches = None
		if self.options.include_arches:
			self.include_arches = set()
			self.include_arches.update(*[x.split() for x in self.options.include_arches])
		self.include_profiles = None
		if self.options.include_profiles:
			self.include_profiles = set()
			self.include_profiles.update(*[x.split() for x in self.options.include_profiles])

		# Disable the "self.modules['Ebuild'].notadded" check when not in commit mode and
		# running `svn status` in every package dir will be too expensive.
		checks['ebuild_notadded'] = not \
			(self.vcs_settings.vcs == "svn" and self.repolevel < 3 and self.options.mode != "commit")

		self.effective_scanlist = scanlist
		if self.options.if_modified == "y":
			self.effective_scanlist = sorted(vcs_files_to_cps(
				chain(self.changed.changed, self.changed.new, self.changed.removed),
				self.repo_settings.repodir,
				self.repolevel, self.reposplit, self.categories))

		# Create our kwargs dict here to initialize the plugins with
		self.kwargs = {
			"repo_settings": self.repo_settings,
			"portdb": self.portdb,
			"qatracker": self.qatracker,
			"vcs_settings": self.vcs_settings,
			"options": self.options,
			"metadata_xsd": get_metadata_xsd(self.repo_settings),
			"uselist": uselist,
			"checks": checks,
			"repo_metadata": self.repo_metadata,
			"profiles": profiles,
			"include_arches": self.include_arches,
			"include_profiles": self.include_profiles,
			"caches": self.caches,
			"repoman_incrementals": self.repoman_incrementals,
			"env": self.env,
			"have": self.have,
			"dev_keywords": self.dev_keywords,
			"linechecks": self.moduleconfig.linechecks,
		}
		# initialize the plugin checks here
		self.modules = {}
		self._ext_futures = {}
		self.pkg_level_futures = None

	def set_kwargs(self, mod):
		'''Creates a limited set of kwargs to pass to the module's __init__()

		@param mod: module name string
		@returns: dictionary
		'''
		kwargs = {}
		for key in self.moduleconfig.controller.modules[mod]['mod_kwargs']:
			kwargs[key] = self.kwargs[key]
		return kwargs

	def set_func_kwargs(self, mod, dynamic_data=None):
		'''Updates the dynamic_data dictionary with any new key, value pairs.
		Creates a limited set of kwargs to pass to the modulefunctions to run

		@param mod: module name string
		@param dynamic_data: dictionary structure
		@returns: dictionary
		'''
		func_kwargs = self.moduleconfig.controller.modules[mod]['func_kwargs']
		# determine new keys
		required = set(list(func_kwargs))
		exist = set(list(dynamic_data))
		new = required.difference(exist)
		# update dynamic_data with initialized entries
		for key in new:
			logging.debug("set_func_kwargs(); adding: %s, %s",
				key, func_kwargs[key])
			if func_kwargs[key][0] in ['Future', 'ExtendedFuture']:
				if key not in self._ext_futures:
					logging.debug(
						"Adding a new key: %s to the ExtendedFuture dict", key)
					self._ext_futures[key] = func_kwargs[key]
				self._set_future(dynamic_data, key, func_kwargs[key])
			else:  # builtin python data type
				dynamic_data[key] = DATA_TYPES[func_kwargs[key][0]]()
		kwargs = {}
		for key in required:
			kwargs[key] = dynamic_data[key]
		return kwargs

	def reset_futures(self, dynamic_data):
		'''Reset any Future data types

		@param dynamic_data: dictionary
		'''
		for key in list(self._ext_futures):
			if key not in self.pkg_level_futures:
				self._set_future(dynamic_data, key, self._ext_futures[key])

	@staticmethod
	def _set_future(dynamic_data, key, data):
		'''Set a dynamic_data key to a new ExtendedFuture instance

		@param dynamic_data: dictionary
		@param key: tuple of (dictionary-key, default-value)
		'''
		if data[0] in ['Future', 'ExtendedFuture']:
			if data[1] in ['UNSET']:
				dynamic_data[key] = ExtendedFuture()
			else:
				if data[1] in DATA_TYPES:
					default = DATA_TYPES[data[1]]()
				else:
					default = data[1]
				dynamic_data[key] = ExtendedFuture(default)

	def scan_pkgs(self, can_force):
		for xpkg in self.effective_scanlist:
			xpkg_continue = False
			# ebuilds and digests added to cvs respectively.
			logging.info("checking package %s", xpkg)
			# save memory by discarding xmatch caches from previous package(s)
			self.caches['arch_xmatch'].clear()
			catdir, pkgdir = xpkg.split("/")
			checkdir = self.repo_settings.repodir + "/" + xpkg
			checkdir_relative = ""
			if self.repolevel < 3:
				checkdir_relative = os.path.join(pkgdir, checkdir_relative)
			if self.repolevel < 2:
				checkdir_relative = os.path.join(catdir, checkdir_relative)
			checkdir_relative = os.path.join(".", checkdir_relative)

			# Run the status check
			if self.kwargs['checks']['ebuild_notadded']:
				self.vcs_settings.status.check(checkdir, checkdir_relative, xpkg)

			if self.generate_manifest:
				if not manifest.Manifest(**self.kwargs).update_manifest(checkdir):
					self.qatracker.add_error("manifest.bad", os.path.join(xpkg, 'Manifest'))
				if self.options.mode == 'manifest':
					continue
			checkdirlist = os.listdir(checkdir)

			dynamic_data = {
				'changelog_modified': False,
				'checkdirlist': ExtendedFuture(checkdirlist),
				'checkdir': checkdir,
				'xpkg': xpkg,
				'changed': self.changed,
				'checkdir_relative': checkdir_relative,
				'can_force': can_force,
				'repolevel': self.repolevel,
				'catdir': catdir,
				'pkgdir': pkgdir,
				'validity_future': ExtendedFuture(True),
				'y_ebuild': None,
				# this needs to be reset at the pkg level only,
				# easiest is to just initialize it here
				'muselist': ExtendedFuture(set()),
				'src_uri_error': ExtendedFuture(),
				}
			self.pkg_level_futures = [
				'checkdirlist',
				'muselist',
				'pkgs',
				'src_uri_error',
				'validity_future',
				]
			# need to set it up for ==> self.modules or some other ordered list
			logging.debug("***** starting pkgs_loop: %s", self.moduleconfig.pkgs_loop)
			for mod in self.moduleconfig.pkgs_loop:
				mod_class = self.moduleconfig.controller.get_class(mod)
				logging.debug("Initializing class name: %s", mod_class.__name__)
				self.modules[mod_class.__name__] = mod_class(**self.set_kwargs(mod))
				logging.debug("scan_pkgs; module: %s", mod_class.__name__)
				do_it, functions = self.modules[mod_class.__name__].runInPkgs
				if do_it:
					for func in functions:
						_continue = func(**self.set_func_kwargs(mod, dynamic_data))
						if _continue:
							# If we can't access all the metadata then it's totally unsafe to
							# commit since there's no way to generate a correct Manifest.
							# Do not try to do any more QA checks on this package since missing
							# metadata leads to false positives for several checks, and false
							# positives confuse users.
							xpkg_continue = True
							break

			if xpkg_continue:
				continue

			# Sort ebuilds in ascending order for the KEYWORDS.dropped check.
			pkgs = dynamic_data['pkgs'].get()
			ebuildlist = sorted(pkgs.values())
			ebuildlist = [pkg.pf for pkg in ebuildlist]

			if self.kwargs['checks']['changelog'] and "ChangeLog" not in checkdirlist:
				self.qatracker.add_error("changelog.missing", xpkg + "/ChangeLog")

			changelog_path = os.path.join(checkdir_relative, "ChangeLog")
			dynamic_data["changelog_modified"] = changelog_path in self.changed.changelogs

			self._scan_ebuilds(ebuildlist, dynamic_data)
		return


	def _scan_ebuilds(self, ebuildlist, dynamic_data):

		for y_ebuild in ebuildlist:
			self.reset_futures(dynamic_data)
			dynamic_data['y_ebuild'] = y_ebuild
			y_ebuild_continue = False

			# initialize per ebuild plugin checks here
			# need to set it up for ==> self.modules_list or some other ordered list
			for mod in self.moduleconfig.ebuilds_loop:
				if mod:
					mod_class = self.moduleconfig.controller.get_class(mod)
					if mod_class.__name__ not in self.modules:
						logging.debug("Initializing class name: %s", mod_class.__name__)
						self.modules[mod_class.__name__] = mod_class(**self.set_kwargs(mod))
				logging.debug("scan_ebuilds: module: %s", mod_class.__name__)
				do_it, functions = self.modules[mod_class.__name__].runInEbuilds
				logging.debug("do_it: %s, functions: %s", do_it, [x.__name__ for x in functions])
				if do_it:
					for func in functions:
						logging.debug("\tRunning function: %s", func)
						_continue = func(**self.set_func_kwargs(mod, dynamic_data))
						if _continue:
							# If we can't access all the metadata then it's totally unsafe to
							# commit since there's no way to generate a correct Manifest.
							# Do not try to do any more QA checks on this package since missing
							# metadata leads to false positives for several checks, and false
							# positives confuse users.
							y_ebuild_continue = True
							# logging.debug("\t>>> Continuing")
							break

			if y_ebuild_continue:
				continue

			logging.debug("Finished ebuild plugin loop, continuing...")

		# Final checks
		# initialize per pkg plugin final checks here
		# need to set it up for ==> self.modules_list or some other ordered list
		xpkg_complete = False
		for mod in self.moduleconfig.final_loop:
			if mod:
				mod_class = self.moduleconfig.controller.get_class(mod)
				if mod_class.__name__ not in self.modules:
					logging.debug("Initializing class name: %s", mod_class.__name__)
					self.modules[mod_class.__name__] = mod_class(**self.set_kwargs(mod))
			logging.debug("scan_ebuilds final checks: module: %s", mod_class.__name__)
			do_it, functions = self.modules[mod_class.__name__].runInFinal
			logging.debug("do_it: %s, functions: %s", do_it, [x.__name__ for x in functions])
			if do_it:
				for func in functions:
					logging.debug("\tRunning function: %s", func)
					_continue = func(**self.set_func_kwargs(mod, dynamic_data))
					if _continue:
						xpkg_complete = True
						# logging.debug("\t>>> Continuing")
						break

		if xpkg_complete:
			return
		return
