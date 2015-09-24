
from __future__ import print_function, unicode_literals

import copy
import io
import logging
import re
import sys
from itertools import chain
from pprint import pformat

from _emerge.Package import Package

import portage
from portage import normalize_path
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.dep import Atom
from portage.output import green
from repoman.checks.directories.files import FileChecks
from repoman.checks.ebuilds.checks import run_checks
from repoman.checks.ebuilds.eclasses.live import LiveEclassChecks
from repoman.checks.ebuilds.eclasses.ruby import RubyEclassChecks
from repoman.checks.ebuilds.fetches import FetchChecks
from repoman.checks.ebuilds.keywords import KeywordChecks
from repoman.checks.ebuilds.isebuild import IsEbuild
from repoman.checks.ebuilds.thirdpartymirrors import ThirdPartyMirrors
from repoman.checks.ebuilds.manifests import Manifests
from repoman.check_missingslot import check_missingslot
from repoman.checks.ebuilds.misc import bad_split_check, pkg_invalid
from repoman.checks.ebuilds.pkgmetadata import PkgMetadata
from repoman.checks.ebuilds.use_flags import USEFlagChecks
from repoman.checks.ebuilds.variables.description import DescriptionChecks
from repoman.checks.ebuilds.variables.eapi import EAPIChecks
from repoman.checks.ebuilds.variables.license import LicenseChecks
from repoman.checks.ebuilds.variables.restrict import RestrictChecks
from repoman.ebuild import Ebuild
from repoman.modules.commit import repochecks
from repoman.profile import check_profiles, dev_profile_keywords, setup_profile
from repoman.qa_data import missingvars, suspect_virtual, suspect_rdepend
from repoman.qa_tracker import QATracker
from repoman.repos import repo_metadata
from repoman.scan import Changes, scan
from repoman.vcs.vcsstatus import VCSStatus
from repoman.vcs.vcs import vcs_files_to_cps

if sys.hexversion >= 0x3000000:
	basestring = str

NON_ASCII_RE = re.compile(r'[^\x00-\x7f]')


def sort_key(item):
	return item[2].sub_path



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
		# We really only need to cache the metadata that's necessary for visibility
		# filtering. Anything else can be discarded to reduce memory consumption.
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

		self.qatracker = QATracker()

		if self.options.echangelog is None and self.repo_settings.repo_config.update_changelog:
			self.options.echangelog = 'y'

		if self.vcs_settings.vcs is None:
			self.options.echangelog = 'n'

		self.check = {}
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
		self.check['changelog'] = not is_echangelog_enabled and self.vcs_settings.vcs_is_cvs_or_svn

		if self.options.mode == "manifest":
			pass
		elif self.options.pretend:
			print(green("\nRepoMan does a once-over of the neighborhood..."))
		else:
			print(green("\nRepoMan scours the neighborhood..."))

		self.changed = Changes(self.options)
		self.changed.scan(self.vcs_settings)

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

		# Disable the "ebuild.notadded" check when not in commit mode and
		# running `svn status` in every package dir will be too expensive.
		self.check['ebuild_notadded'] = not \
			(self.vcs_settings.vcs == "svn" and self.repolevel < 3 and self.options.mode != "commit")

		self.effective_scanlist = scanlist
		if self.options.if_modified == "y":
			self.effective_scanlist = sorted(vcs_files_to_cps(
				chain(self.changed.changed, self.changed.new, self.changed.removed),
				self.repolevel, self.reposplit, self.categories))

		self.live_eclasses = portage.const.LIVE_ECLASSES

		# initialize our checks classes here before the big xpkg loop
		self.manifester = Manifests(self.options, self.qatracker, self.repo_settings.repoman_settings)
		self.is_ebuild = IsEbuild(self.repo_settings.repoman_settings, self.repo_settings, self.portdb, self.qatracker)
		self.filescheck = FileChecks(
			self.qatracker, self.repo_settings.repoman_settings, self.repo_settings, self.portdb, self.vcs_settings)
		self.status_check = VCSStatus(self.vcs_settings, self.qatracker)
		self.fetchcheck = FetchChecks(
			self.qatracker, self.repo_settings, self.portdb, self.vcs_settings)
		self.pkgmeta = PkgMetadata(self.options, self.qatracker, self.repo_settings.repoman_settings)
		self.thirdparty = ThirdPartyMirrors(self.repo_settings.repoman_settings, self.qatracker)
		self.use_flag_checks = USEFlagChecks(self.qatracker, uselist)
		self.keywordcheck = KeywordChecks(self.qatracker, self.options)
		self.liveeclasscheck = LiveEclassChecks(self.qatracker)
		self.rubyeclasscheck = RubyEclassChecks(self.qatracker)
		self.eapicheck = EAPIChecks(self.qatracker, self.repo_settings)
		self.descriptioncheck = DescriptionChecks(self.qatracker)
		self.licensecheck = LicenseChecks(self.qatracker, liclist, liclist_deprecated)
		self.restrictcheck = RestrictChecks(self.qatracker)


	def scan_pkgs(self, can_force):
		for xpkg in self.effective_scanlist:
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

			if self.manifester.run(checkdir, self.portdb):
				continue
			if not self.manifester.generated_manifest:
				self.manifester.digest_check(xpkg, checkdir)
			if self.options.mode == 'manifest-check':
				continue

			checkdirlist = os.listdir(checkdir)

			self.pkgs, self.allvalid = self.is_ebuild.check(checkdirlist, checkdir, xpkg)
			if self.is_ebuild.continue_:
				# If we can't access all the metadata then it's totally unsafe to
				# commit since there's no way to generate a correct Manifest.
				# Do not try to do any more QA checks on this package since missing
				# metadata leads to false positives for several checks, and false
				# positives confuse users.
				can_force = False
				continue

			self.keywordcheck.prepare()

			# Sort ebuilds in ascending order for the KEYWORDS.dropped check.
			ebuildlist = sorted(self.pkgs.values())
			ebuildlist = [pkg.pf for pkg in ebuildlist]

			self.filescheck.check(
				checkdir, checkdirlist, checkdir_relative, self.changed.changed, self.changed.new)

			self.status_check.check(self.check['ebuild_notadded'], checkdir, checkdir_relative, xpkg)
			self.eadded.extend(self.status_check.eadded)

			self.fetchcheck.check(
				xpkg, checkdir, checkdir_relative, self.changed.changed, self.changed.new)

			if self.check['changelog'] and "ChangeLog" not in checkdirlist:
				self.qatracker.add_error("changelog.missing", xpkg + "/ChangeLog")

			self.pkgmeta.check(xpkg, checkdir, checkdirlist, self.repolevel)
			self.muselist = frozenset(self.pkgmeta.musedict)

			changelog_path = os.path.join(checkdir_relative, "ChangeLog")
			self.changelog_modified = changelog_path in self.changed.changelogs

			self._scan_ebuilds(ebuildlist, xpkg, catdir, pkgdir)
		return self.qatracker, can_force


	def _scan_ebuilds(self, ebuildlist, xpkg, catdir, pkgdir):
		# detect unused local USE-descriptions
		used_useflags = set()

		for y_ebuild in ebuildlist:

			ebuild = Ebuild(
				self.repo_settings, self.repolevel, pkgdir, catdir, self.vcs_settings,
				xpkg, y_ebuild)

			if self.check['changelog'] and not self.changelog_modified \
				and ebuild.ebuild_path in self.changed.new_ebuilds:
				self.qatracker.add_error('changelog.ebuildadded', ebuild.relative_path)

			if ebuild.untracked(self.check['ebuild_notadded'], y_ebuild, self.eadded):
				# ebuild not added to vcs
				self.qatracker.add_error(
					"ebuild.notadded", xpkg + "/" + y_ebuild + ".ebuild")

			if bad_split_check(xpkg, y_ebuild, pkgdir, self.qatracker):
				continue

			pkg = self.pkgs[y_ebuild]
			if pkg_invalid(pkg, self.qatracker, ebuild):
				self.allvalid = False
				continue

			myaux = pkg._metadata
			eapi = myaux["EAPI"]
			inherited = pkg.inherited
			live_ebuild = self.live_eclasses.intersection(inherited)

			self.eapicheck.check(pkg, ebuild)

			for k, v in myaux.items():
				if not isinstance(v, basestring):
					continue
				m = NON_ASCII_RE.search(v)
				if m is not None:
					self.qatracker.add_error(
						"variable.invalidchar",
						"%s: %s variable contains non-ASCII "
						"character at position %s" %
						(ebuild.relative_path, k, m.start() + 1))

			if not self.fetchcheck.src_uri_error:
				self.thirdparty.check(myaux, ebuild.relative_path)

			if myaux.get("PROVIDE"):
				self.qatracker.add_error("virtual.oldstyle", ebuild.relative_path)

			for pos, missing_var in enumerate(missingvars):
				if not myaux.get(missing_var):
					if catdir == "virtual" and \
						missing_var in ("HOMEPAGE", "LICENSE"):
						continue
					if live_ebuild and missing_var == "KEYWORDS":
						continue
					myqakey = missingvars[pos] + ".missing"
					self.qatracker.add_error(myqakey, xpkg + "/" + y_ebuild + ".ebuild")

			if catdir == "virtual":
				for var in ("HOMEPAGE", "LICENSE"):
					if myaux.get(var):
						myqakey = var + ".virtual"
						self.qatracker.add_error(myqakey, ebuild.relative_path)

			self.descriptioncheck.check(pkg, ebuild)

			keywords = myaux["KEYWORDS"].split()

			ebuild_archs = set(
				kw.lstrip("~") for kw in keywords if not kw.startswith("-"))

			self.keywordcheck.check(
				pkg, xpkg, ebuild, y_ebuild, keywords, ebuild_archs, self.changed,
				live_ebuild, self.repo_metadata['kwlist'], self.profiles)

			if live_ebuild and self.repo_settings.repo_config.name == "gentoo":
				self.liveeclasscheck.check(
					pkg, xpkg, ebuild, y_ebuild, keywords, self.repo_metadata['pmaskdict'])

			if self.options.ignore_arches:
				arches = [[
					self.repo_settings.repoman_settings["ARCH"], self.repo_settings.repoman_settings["ARCH"],
					self.repo_settings.repoman_settings["ACCEPT_KEYWORDS"].split()]]
			else:
				arches = set()
				for keyword in keywords:
					if keyword[0] == "-":
						continue
					elif keyword[0] == "~":
						arch = keyword[1:]
						if arch == "*":
							for expanded_arch in self.profiles:
								if expanded_arch == "**":
									continue
								arches.add(
									(keyword, expanded_arch, (
										expanded_arch, "~" + expanded_arch)))
						else:
							arches.add((keyword, arch, (arch, keyword)))
					else:
						if keyword == "*":
							for expanded_arch in self.profiles:
								if expanded_arch == "**":
									continue
								arches.add(
									(keyword, expanded_arch, (expanded_arch,)))
						else:
							arches.add((keyword, keyword, (keyword,)))
				if not arches:
					# Use an empty profile for checking dependencies of
					# packages that have empty KEYWORDS.
					arches.add(('**', '**', ('**',)))

			unknown_pkgs = set()
			baddepsyntax = False
			badlicsyntax = False
			badprovsyntax = False
			# catpkg = catdir + "/" + y_ebuild

			inherited_java_eclass = "java-pkg-2" in inherited or \
				"java-pkg-opt-2" in inherited
			inherited_wxwidgets_eclass = "wxwidgets" in inherited
			# operator_tokens = set(["||", "(", ")"])
			type_list, badsyntax = [], []
			for mytype in Package._dep_keys + ("LICENSE", "PROPERTIES", "PROVIDE"):
				mydepstr = myaux[mytype]

				buildtime = mytype in Package._buildtime_keys
				runtime = mytype in Package._runtime_keys
				token_class = None
				if mytype.endswith("DEPEND"):
					token_class = portage.dep.Atom

				try:
					atoms = portage.dep.use_reduce(
						mydepstr, matchall=1, flat=True,
						is_valid_flag=pkg.iuse.is_valid_flag, token_class=token_class)
				except portage.exception.InvalidDependString as e:
					atoms = None
					badsyntax.append(str(e))

				if atoms and mytype.endswith("DEPEND"):
					if runtime and \
						"test?" in mydepstr.split():
						self.qatracker.add_error(
							mytype + '.suspect',
							"%s: 'test?' USE conditional in %s" %
							(ebuild.relative_path, mytype))

					for atom in atoms:
						if atom == "||":
							continue

						is_blocker = atom.blocker

						# Skip dependency.unknown for blockers, so that we
						# don't encourage people to remove necessary blockers,
						# as discussed in bug 382407. We use atom.without_use
						# due to bug 525376.
						if not is_blocker and \
							not self.portdb.xmatch("match-all", atom.without_use) and \
							not atom.cp.startswith("virtual/"):
							unknown_pkgs.add((mytype, atom.unevaluated_atom))

						if catdir != "virtual":
							if not is_blocker and \
								atom.cp in suspect_virtual:
								self.qatracker.add_error(
									'virtual.suspect', ebuild.relative_path +
									": %s: consider using '%s' instead of '%s'" %
									(mytype, suspect_virtual[atom.cp], atom))
							if not is_blocker and \
								atom.cp.startswith("perl-core/"):
								self.qatracker.add_error('dependency.perlcore',
									ebuild.relative_path +
									": %s: please use '%s' instead of '%s'" %
									(mytype,
									atom.replace("perl-core/","virtual/perl-"),
									atom))

						if buildtime and \
							not is_blocker and \
							not inherited_java_eclass and \
							atom.cp == "virtual/jdk":
							self.qatracker.add_error(
								'java.eclassesnotused', ebuild.relative_path)
						elif buildtime and \
							not is_blocker and \
							not inherited_wxwidgets_eclass and \
							atom.cp == "x11-libs/wxGTK":
							self.qatracker.add_error(
								'wxwidgets.eclassnotused',
								"%s: %ss on x11-libs/wxGTK without inheriting"
								" wxwidgets.eclass" % (ebuild.relative_path, mytype))
						elif runtime:
							if not is_blocker and \
								atom.cp in suspect_rdepend:
								self.qatracker.add_error(
									mytype + '.suspect',
									ebuild.relative_path + ": '%s'" % atom)

						if atom.operator == "~" and \
							portage.versions.catpkgsplit(atom.cpv)[3] != "r0":
							qacat = 'dependency.badtilde'
							self.qatracker.add_error(
								qacat, "%s: %s uses the ~ operator"
								" with a non-zero revision: '%s'" %
								(ebuild.relative_path, mytype, atom))

						check_missingslot(atom, mytype, eapi, self.portdb, self.qatracker,
							ebuild.relative_path, myaux)

				type_list.extend([mytype] * (len(badsyntax) - len(type_list)))

			for m, b in zip(type_list, badsyntax):
				if m.endswith("DEPEND"):
					qacat = "dependency.syntax"
				else:
					qacat = m + ".syntax"
				self.qatracker.add_error(
					qacat, "%s: %s: %s" % (ebuild.relative_path, m, b))

			badlicsyntax = len([z for z in type_list if z == "LICENSE"])
			badprovsyntax = len([z for z in type_list if z == "PROVIDE"])
			baddepsyntax = len(type_list) != badlicsyntax + badprovsyntax
			badlicsyntax = badlicsyntax > 0
			badprovsyntax = badprovsyntax > 0

			self.use_flag_checks.check(pkg, xpkg, ebuild, y_ebuild, self.muselist)

			ebuild_used_useflags = self.use_flag_checks.getUsedUseFlags()
			used_useflags = used_useflags.union(ebuild_used_useflags)

			self.rubyeclasscheck.check(pkg, ebuild)

			# license checks
			if not badlicsyntax:
				self.licensecheck.check(pkg, xpkg, ebuild, y_ebuild)

			self.restrictcheck.check(pkg, xpkg, ebuild, y_ebuild)

			# Syntax Checks
			if not self.vcs_settings.vcs_preserves_mtime:
				if ebuild.ebuild_path not in self.changed.new_ebuilds and \
					ebuild.ebuild_path not in self.changed.ebuilds:
					pkg.mtime = None
			try:
				# All ebuilds should have utf_8 encoding.
				f = io.open(
					_unicode_encode(
						ebuild.full_path, encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'])
				try:
					for check_name, e in run_checks(f, pkg):
						self.qatracker.add_error(
							check_name, ebuild.relative_path + ': %s' % e)
				finally:
					f.close()
			except UnicodeDecodeError:
				# A file.UTF8 failure will have already been recorded above.
				pass

			if self.options.force:
				# The dep_check() calls are the most expensive QA test. If --force
				# is enabled, there's no point in wasting time on these since the
				# user is intent on forcing the commit anyway.
				continue

			relevant_profiles = []
			for keyword, arch, groups in arches:
				if arch not in self.profiles:
					# A missing profile will create an error further down
					# during the KEYWORDS verification.
					continue

				if self.include_arches is not None:
					if arch not in self.include_arches:
						continue

				relevant_profiles.extend(
					(keyword, groups, prof) for prof in self.profiles[arch])

			relevant_profiles.sort(key=sort_key)

			for keyword, groups, prof in relevant_profiles:

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
						config_root=self.config_root,
						local_config=False,
						_unmatched_removal=self.options.unmatched_removal,
						env=self.env, repositories=self.repo_settings.repoman_settings.repositories)
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

				if not baddepsyntax:
					ismasked = not ebuild_archs or \
						pkg.cpv not in self.portdb.xmatch("match-visible",
						Atom("%s::%s" % (pkg.cp, self.repo_settings.repo_config.name)))
					if ismasked:
						if not self.have['pmasked']:
							self.have['pmasked'] = bool(dep_settings._getMaskAtom(
								pkg.cpv, pkg._metadata))
						if self.options.ignore_masked:
							continue
						# we are testing deps for a masked package; give it some lee-way
						suffix = "masked"
						matchmode = "minimum-all"
					else:
						suffix = ""
						matchmode = "minimum-visible"

					if not self.have['dev_keywords']:
						self.have['dev_keywords'] = \
							bool(self.dev_keywords.intersection(keywords))

					if prof.status == "dev":
						suffix = suffix + "indev"

					for mytype in Package._dep_keys:

						mykey = "dependency.bad" + suffix
						myvalue = myaux[mytype]
						if not myvalue:
							continue

						success, atoms = portage.dep_check(
							myvalue, self.portdb, dep_settings,
							use="all", mode=matchmode, trees=self.repo_settings.trees)

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
								atoms = [
									str(atom.unevaluated_atom)
									for atom in atoms if not atom.blocker]

								# if we emptied out our list, continue:
								if not atoms:
									continue
								self.qatracker.add_error(mykey,
									"%s: %s: %s(%s)\n%s"
									% (ebuild.relative_path, mytype, keyword, prof,
										pformat(atoms, indent=6)))
						else:
							self.qatracker.add_error(mykey,
								"%s: %s: %s(%s)\n%s"
								% (ebuild.relative_path, mytype, keyword, prof,
									pformat(atoms, indent=6)))

			if not baddepsyntax and unknown_pkgs:
				type_map = {}
				for mytype, atom in unknown_pkgs:
					type_map.setdefault(mytype, set()).add(atom)
				for mytype, atoms in type_map.items():
					self.qatracker.add_error(
						"dependency.unknown", "%s: %s: %s"
						% (ebuild.relative_path, mytype, ", ".join(sorted(atoms))))

		# check if there are unused local USE-descriptions in metadata.xml
		# (unless there are any invalids, to avoid noise)
		if self.allvalid:
			for myflag in self.muselist.difference(used_useflags):
				self.qatracker.add_error(
					"metadata.warning",
					"%s/metadata.xml: unused local USE-description: '%s'"
					% (xpkg, myflag))
