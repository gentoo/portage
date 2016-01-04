# -*- coding:utf-8 -*-

from __future__ import print_function, unicode_literals

import logging
from itertools import chain

import portage
from portage import normalize_path
from portage import os
from portage.output import green
from repoman.modules.commit import repochecks
from repoman.profile import check_profiles, dev_profile_keywords, setup_profile
from repoman.repos import repo_metadata
from repoman.modules.scan.scan import scan
from repoman.modules.vcs.vcs import vcs_files_to_cps

from portage.module import Modules

MODULES_PATH = os.path.join(os.path.dirname(__file__), "modules", "scan")
# initial development debug info
#print("module path:", path)

MODULE_CONTROLLER = Modules(path=MODULES_PATH, namepath="repoman.modules.scan")

# initial development debug info
#print(module_controller.module_names)
MODULE_NAMES = MODULE_CONTROLLER.module_names[:]


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

		metadata_dtd = None
		for path in reversed(self.repo_settings.repo_config.eclass_db.porttrees):
			path = os.path.join(path, 'metadata/dtd/metadata.dtd')
			if os.path.exists(path):
				metadata_dtd = path
				break

		self.portdb = repo_settings.portdb
		self.portdb.settings = self.repo_settings.repoman_settings
		# We really only need to cache the metadata that's necessary for visibility
		# filtering. Anything else can be discarded to reduce memory consumption.
		if self.options.mode != "manifest" and self.options.digest != "y":
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
		}

		self.repo_settings.repoman_settings['PORTAGE_ARCHLIST'] = ' '.join(sorted(kwlist))
		self.repo_settings.repoman_settings.backup_changes('PORTAGE_ARCHLIST')

		self.profiles = setup_profile(profile_list)

		check_profiles(self.profiles, self.repo_settings.repoman_settings.archlist())

		scanlist = scan(self.repolevel, self.reposplit, startdir, self.categories, self.repo_settings)

		self.dev_keywords = dev_profile_keywords(self.profiles)

		self.qatracker = self.vcs_settings.qatracker

		if self.options.echangelog is None and self.repo_settings.repo_config.update_changelog:
			self.options.echangelog = 'y'

		if self.vcs_settings.vcs is None:
			self.options.echangelog = 'n'

		self.checks = {}
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
		self.checks['changelog'] = not is_echangelog_enabled and self.vcs_settings.vcs_is_cvs_or_svn

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

		# Disable the "self.modules['Ebuild'].notadded" check when not in commit mode and
		# running `svn status` in every package dir will be too expensive.
		self.checks['ebuild_notadded'] = not \
			(self.vcs_settings.vcs == "svn" and self.repolevel < 3 and self.options.mode != "commit")

		self.effective_scanlist = scanlist
		if self.options.if_modified == "y":
			self.effective_scanlist = sorted(vcs_files_to_cps(
				chain(self.changed.changed, self.changed.new, self.changed.removed),
				self.repolevel, self.reposplit, self.categories))

		# Create our kwargs dict here to initialize the plugins with
		self.kwargs = {
			"repo_settings": self.repo_settings,
			"portdb": self.portdb,
			"qatracker": self.qatracker,
			"vcs_settings": self.vcs_settings,
			"options": self.options,
			"metadata_dtd": metadata_dtd,
			"uselist": uselist,
			"checks": self.checks,
			"repo_metadata": self.repo_metadata,
			"profiles": self.profiles,
			"include_arches": self.include_arches,
			"caches": self.caches,
			"repoman_incrementals": self.repoman_incrementals,
			"env": self.env,
			"have": self.have,
			"dev_keywords": self.dev_keywords,
		}
		# initialize the plugin checks here
		self.modules = {}
		for mod in ['manifests', 'isebuild', 'keywords', 'files', 'vcsstatus',
					'fetches', 'pkgmetadata']:
			mod_class = MODULE_CONTROLLER.get_class(mod)
			print("Initializing class name:", mod_class.__name__)
			self.modules[mod_class.__name__] = mod_class(**self.kwargs)

	def scan_pkgs(self, can_force):
		dynamic_data = {'can_force': can_force}
		for xpkg in self.effective_scanlist:
			xpkg_continue = False
			# ebuilds and digests added to cvs respectively.
			logging.info("checking package %s" % xpkg)
			# save memory by discarding xmatch caches from previous package(s)
			self.caches['arch_xmatch'].clear()
			self.eadded = []
			catdir, pkgdir = xpkg.split("/")
			checkdir = self.repo_settings.repodir + "/" + xpkg
			checkdir_relative = ""
			if self.repolevel < 3:
				checkdir_relative = os.path.join(pkgdir, checkdir_relative)
			if self.repolevel < 2:
				checkdir_relative = os.path.join(catdir, checkdir_relative)
			checkdir_relative = os.path.join(".", checkdir_relative)
			checkdirlist = os.listdir(checkdir)

			dynamic_data = {
				'checkdirlist': checkdirlist,
				'checkdir': checkdir,
				'xpkg': xpkg,
				'changed': self.changed,
				'checkdir_relative': checkdir_relative,
				'can_force': can_force,
				'repolevel': self.repolevel,
				'catdir': catdir,
				'pkgdir': pkgdir,
				}
			# need to set it up for ==> self.modules or some other ordered list
			for mod in ['Manifests', 'IsEbuild', 'KeywordChecks', 'FileChecks',
						'VCSStatus', 'FetchChecks', 'PkgMetadata']:
				print("scan_pkgs(): module:", mod)
				do_it, functions = self.modules[mod].runInPkgs
				if do_it:
					for func in functions:
						rdata = func(**dynamic_data)
						if rdata.get('continue', False):
							# If we can't access all the metadata then it's totally unsafe to
							# commit since there's no way to generate a correct Manifest.
							# Do not try to do any more QA checks on this package since missing
							# metadata leads to false positives for several checks, and false
							# positives confuse users.
							xpkg_continue = True
							break
						dynamic_data.update(rdata)

			if xpkg_continue:
				continue

			# Sort ebuilds in ascending order for the KEYWORDS.dropped check.
			self.pkgs = dynamic_data['pkgs']
			ebuildlist = sorted(self.pkgs.values())
			ebuildlist = [pkg.pf for pkg in ebuildlist]

			if self.checks['changelog'] and "ChangeLog" not in checkdirlist:
				self.qatracker.add_error("changelog.missing", xpkg + "/ChangeLog")

			changelog_path = os.path.join(checkdir_relative, "ChangeLog")
			self.changelog_modified = changelog_path in self.changed.changelogs

			self._scan_ebuilds(ebuildlist, dynamic_data)
		return dynamic_data['can_force']


	def _scan_ebuilds(self, ebuildlist, dynamic_data):
		xpkg = dynamic_data['xpkg']
		# detect unused local USE-descriptions
		dynamic_data['used_useflags'] = set()

		for y_ebuild in ebuildlist:
			dynamic_data['y_ebuild'] = y_ebuild
			y_ebuild_continue = False

			# initialize per ebuild plugin checks here
			# need to set it up for ==> self.modules_list or some other ordered list
			for mod in [('ebuild', 'Ebuild'), ('live', 'LiveEclassChecks'),
				('eapi', 'EAPIChecks'), ('ebuild_metadata', 'EbuildMetadata'),
				('thirdpartymirrors', 'ThirdPartyMirrors'),
				('description', 'DescriptionChecks'), (None, 'KeywordChecks'),
				('arches', 'ArchChecks'), ('depend', 'DependChecks'),
				('use_flags', 'USEFlagChecks'), ('ruby', 'RubyEclassChecks'),
				('license', 'LicenseChecks'), ('restrict', 'RestrictChecks'),
				('mtime', 'MtimeChecks'), ('multicheck', 'MultiCheck'),
				# Options.is_forced() is used to bypass further checks
				('options', 'Options'), ('profile', 'ProfileDependsChecks'),
				]:
				if mod[0]:
					mod_class = MODULE_CONTROLLER.get_class(mod[0])
					logging.debug("Initializing class name: %s", mod_class.__name__)
					self.modules[mod[1]] = mod_class(**self.kwargs)
				logging.debug("scan_ebuilds: module: %s", mod[1])
				do_it, functions = self.modules[mod[1]].runInEbuilds
				logging.debug("do_it: %s, functions: %s", do_it, [x.__name__ for x in functions])
				if do_it:
					for func in functions:
						print("\tRunning function:", func)
						rdata = func(**dynamic_data)
						if rdata.get('continue', False):
							# If we can't access all the metadata then it's totally unsafe to
							# commit since there's no way to generate a correct Manifest.
							# Do not try to do any more QA checks on this package since missing
							# metadata leads to false positives for several checks, and false
							# positives confuse users.
							y_ebuild_continue = True
							break
						#print("rdata:", rdata)
						dynamic_data.update(rdata)
						#print("dynamic_data", dynamic_data)

			if y_ebuild_continue:
				continue

			if not dynamic_data['baddepsyntax'] and dynamic_data['unknown_pkgs']:
				type_map = {}
				for mytype, atom in dynamic_data['unknown_pkgs']:
					type_map.setdefault(mytype, set()).add(atom)
				for mytype, atoms in type_map.items():
					self.qatracker.add_error(
						"dependency.unknown", "%s: %s: %s"
						% (dynamic_data['ebuild'].relative_path, mytype, ", ".join(sorted(atoms))))

		# check if there are unused local USE-descriptions in metadata.xml
		# (unless there are any invalids, to avoid noise)
		if dynamic_data['allvalid']:
			for myflag in dynamic_data['muselist'].difference(dynamic_data['used_useflags']):
				self.qatracker.add_error(
					"metadata.warning",
					"%s/metadata.xml: unused local USE-description: '%s'"
					% (xpkg, myflag))
