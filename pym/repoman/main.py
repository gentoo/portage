#!/usr/bin/python -bO
# Copyright 1999-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function, unicode_literals

import copy
import errno
import io
import logging
import re
import signal
import subprocess
import sys
import tempfile
import platform
from itertools import chain
from pprint import pformat

from os import path as osp
if osp.isfile(osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), ".portage_not_installed")):
	pym_path = osp.join(osp.dirname(osp.dirname(osp.realpath(__file__)))) #, "pym")
	sys.path.insert(0, pym_path)
# import our centrally initialized portage instance
from repoman._portage import portage
portage._internal_caller = True
portage._disable_legacy_globals()


from portage import os
from portage import _encodings
from portage import _unicode_encode
from _emerge.Package import Package
from _emerge.UserQuery import UserQuery
import portage.checksum
import portage.const
import portage.repository.config
from portage import cvstree, normalize_path
from portage import util
from portage.dep import Atom
from portage.exception import MissingParameter
from portage.process import find_binary, spawn
from portage.output import (
	bold, create_color_func, green, nocolor, red)
from portage.output import ConsoleStyleFile, StyleWriter
from portage.util import formatter
from portage.util import writemsg_level
from portage.package.ebuild.digestgen import digestgen

from repoman.argparser import parse_args
from repoman.checks.directories.files import FileChecks
from repoman.checks.ebuilds.checks import run_checks, checks_init
from repoman.checks.ebuilds.eclasses.live import LiveEclassChecks
from repoman.checks.ebuilds.fetches import FetchChecks
from repoman.checks.ebuilds.keywords import KeywordChecks
from repoman.checks.ebuilds.isebuild import IsEbuild
from repoman.checks.ebuilds.thirdpartymirrors import ThirdPartyMirrors
from repoman.checks.ebuilds.manifests import Manifests
from repoman.check_missingslot import check_missingslot
from repoman.checks.ebuilds.misc import bad_split_check, pkg_invalid
from repoman.checks.ebuilds.pkgmetadata import PkgMetadata
from repoman.checks.ebuilds.use_flags import USEFlagChecks
from repoman.ebuild import Ebuild
from repoman.errors import err
from repoman.modules.commit import repochecks
from repoman.profile import check_profiles, dev_keywords, setup_profile
from repoman.qa_data import (
	format_qa_output, format_qa_output_column, qahelp,
	qawarnings, qacats, max_desc_len, missingvars,
	ruby_deprecated, suspect_virtual, suspect_rdepend, valid_restrict)
from repoman.qa_tracker import QATracker
from repoman.repos import RepoSettings, repo_metadata
from repoman.scan import Changes, scan
from repoman._subprocess import repoman_popen, repoman_getstatusoutput
from repoman import utilities
from repoman.vcs.vcs import (
	git_supports_gpg_sign, vcs_files_to_cps, VCSSettings)
from repoman.vcs.vcsstatus import VCSStatus


if sys.hexversion >= 0x3000000:
	basestring = str

util.initialize_logger()

commitmessage = None

bad = create_color_func("BAD")

live_eclasses = portage.const.LIVE_ECLASSES
non_ascii_re = re.compile(r'[^\x00-\x7f]')

# A sane umask is needed for files that portage creates.
os.umask(0o22)
# Repoman sets it's own ACCEPT_KEYWORDS and we don't want it to
# behave incrementally.
repoman_incrementals = tuple(
	x for x in portage.const.INCREMENTALS if x != 'ACCEPT_KEYWORDS')
config_root = os.environ.get("PORTAGE_CONFIGROOT")
repoman_settings = portage.config(config_root=config_root, local_config=False)

if repoman_settings.get("NOCOLOR", "").lower() in ("yes", "true") or \
	repoman_settings.get('TERM') == 'dumb' or \
	not sys.stdout.isatty():
	nocolor()

options, arguments = parse_args(
	sys.argv, qahelp, repoman_settings.get("REPOMAN_DEFAULT_OPTS", ""))

if options.version:
	print("Portage", portage.VERSION)
	sys.exit(0)

if options.experimental_inherit == 'y':
	# This is experimental, so it's non-fatal.
	qawarnings.add("inherit.missing")
	checks_init(experimental_inherit=True)

# Set this to False when an extraordinary issue (generally
# something other than a QA issue) makes it impossible to
# commit (like if Manifest generation fails).
can_force = True

portdir, portdir_overlay, mydir = utilities.FindPortdir(repoman_settings)
if portdir is None:
	sys.exit(1)

myreporoot = os.path.basename(portdir_overlay)
myreporoot += mydir[len(portdir_overlay):]
##################

vcs_settings = VCSSettings(options, repoman_settings)


##################

repo_settings = RepoSettings(config_root, portdir, portdir_overlay,
		repoman_settings, vcs_settings, options, qawarnings)

repoman_settings = repo_settings.repoman_settings

portdb = repo_settings.portdb
##################


if options.echangelog is None and repo_settings.repo_config.update_changelog:
	options.echangelog = 'y'

if vcs_settings.vcs is None:
	options.echangelog = 'n'

# The --echangelog option causes automatic ChangeLog generation,
# which invalidates changelog.ebuildadded and changelog.missing
# checks.
# Note: Some don't use ChangeLogs in distributed SCMs.
# It will be generated on server side from scm log,
# before package moves to the rsync server.
# This is needed because they try to avoid merge collisions.
# Gentoo's Council decided to always use the ChangeLog file.
# TODO: shouldn't this just be switched on the repo, iso the VCS?
is_echangelog_enabled = options.echangelog in ('y', 'force')
vcs_settings.vcs_is_cvs_or_svn = vcs_settings.vcs in ('cvs', 'svn')
check_changelog = not is_echangelog_enabled and vcs_settings.vcs_is_cvs_or_svn

if 'digest' in repoman_settings.features and options.digest != 'n':
	options.digest = 'y'

logging.debug("vcs: %s" % (vcs_settings.vcs,))
logging.debug("repo config: %s" % (repo_settings.repo_config,))
logging.debug("options: %s" % (options,))

# It's confusing if these warnings are displayed without the user
# being told which profile they come from, so disable them.
env = os.environ.copy()
env['FEATURES'] = env.get('FEATURES', '') + ' -unknown-features-warn'

categories = []
for path in repo_settings.repo_config.eclass_db.porttrees:
	categories.extend(portage.util.grabfile(
		os.path.join(path, 'profiles', 'categories')))
repoman_settings.categories = frozenset(
	portage.util.stack_lists([categories], incremental=1))
categories = repoman_settings.categories

portdb.settings = repoman_settings
# We really only need to cache the metadata that's necessary for visibility
# filtering. Anything else can be discarded to reduce memory consumption.
portdb._aux_cache_keys.clear()
portdb._aux_cache_keys.update(
	["EAPI", "IUSE", "KEYWORDS", "repository", "SLOT"])

reposplit = myreporoot.split(os.path.sep)
repolevel = len(reposplit)

###################

if options.mode == 'commit':
	repochecks.commit_check(repolevel, reposplit)
	repochecks.conflict_check(vcs_settings, options)

###################

# Make startdir relative to the canonical repodir, so that we can pass
# it to digestgen and it won't have to be canonicalized again.
if repolevel == 1:
	startdir = repo_settings.repodir
else:
	startdir = normalize_path(mydir)
	startdir = os.path.join(repo_settings.repodir, *startdir.split(os.sep)[-2 - repolevel + 3:])
###################

# get lists of valid keywords, licenses, and use
new_data = repo_metadata(repo_settings.portdb, repoman_settings)
kwlist, liclist, uselist, profile_list, global_pmaskdict, liclist_deprecated = new_data

repoman_settings['PORTAGE_ARCHLIST'] = ' '.join(sorted(kwlist))
repoman_settings.backup_changes('PORTAGE_ARCHLIST')

####################

profiles = setup_profile(profile_list)

####################

check_profiles(profiles, repoman_settings.archlist())

####################

scanlist = scan(repolevel, reposplit, startdir, categories, repo_settings)

####################

dev_keywords = dev_keywords(profiles)

qatracker = QATracker()


if options.mode == "manifest":
	pass
elif options.pretend:
	print(green("\nRepoMan does a once-over of the neighborhood..."))
else:
	print(green("\nRepoMan scours the neighborhood..."))

#####################

changed = Changes(options)
changed.scan(vcs_settings)

######################

have_pmasked = False
have_dev_keywords = False
dofail = 0

# NOTE: match-all caches are not shared due to potential
# differences between profiles in _get_implicit_iuse.
arch_caches = {}
arch_xmatch_caches = {}
shared_xmatch_caches = {"cp-list": {}}

include_arches = None
if options.include_arches:
	include_arches = set()
	include_arches.update(*[x.split() for x in options.include_arches])

# Disable the "ebuild.notadded" check when not in commit mode and
# running `svn status` in every package dir will be too expensive.

check_ebuild_notadded = not \
	(vcs_settings.vcs == "svn" and repolevel < 3 and options.mode != "commit")

effective_scanlist = scanlist
if options.if_modified == "y":
	effective_scanlist = sorted(vcs_files_to_cps(
		chain(changed.changed, changed.new, changed.removed),
		repolevel, reposplit, categories))

######################
# initialize our checks classes here before the big xpkg loop
manifester = Manifests(options, qatracker, repoman_settings)
is_ebuild = IsEbuild(repoman_settings, repo_settings, portdb, qatracker)
filescheck = FileChecks(
	qatracker, repoman_settings, repo_settings, portdb, vcs_settings)
status_check = VCSStatus(vcs_settings, qatracker)
fetchcheck = FetchChecks(
	qatracker, repoman_settings, repo_settings, portdb, vcs_settings)
pkgmeta = PkgMetadata(options, qatracker, repoman_settings)
thirdparty = ThirdPartyMirrors(repoman_settings, qatracker)
use_flag_checks = USEFlagChecks(qatracker, uselist)
keywordcheck = KeywordChecks(qatracker, options)
liveeclasscheck = LiveEclassChecks(qatracker)
######################

for xpkg in effective_scanlist:
	# ebuilds and digests added to cvs respectively.
	logging.info("checking package %s" % xpkg)
	# save memory by discarding xmatch caches from previous package(s)
	arch_xmatch_caches.clear()
	eadded = []
	catdir, pkgdir = xpkg.split("/")
	checkdir = repo_settings.repodir + "/" + xpkg
	checkdir_relative = ""
	if repolevel < 3:
		checkdir_relative = os.path.join(pkgdir, checkdir_relative)
	if repolevel < 2:
		checkdir_relative = os.path.join(catdir, checkdir_relative)
	checkdir_relative = os.path.join(".", checkdir_relative)

#####################
	if manifester.run(checkdir, portdb):
		continue
	if not manifester.generated_manifest:
		manifester.digest_check(xpkg, checkdir)
######################

	if options.mode == 'manifest-check':
		continue

	checkdirlist = os.listdir(checkdir)

######################
	pkgs, allvalid = is_ebuild.check(checkdirlist, checkdir, xpkg)
	if is_ebuild.continue_:
		# If we can't access all the metadata then it's totally unsafe to
		# commit since there's no way to generate a correct Manifest.
		# Do not try to do any more QA checks on this package since missing
		# metadata leads to false positives for several checks, and false
		# positives confuse users.
		can_force = False
		continue
######################

	keywordcheck.prepare()

	# Sort ebuilds in ascending order for the KEYWORDS.dropped check.
	ebuildlist = sorted(pkgs.values())
	ebuildlist = [pkg.pf for pkg in ebuildlist]
#######################
	filescheck.check(checkdir, checkdirlist, checkdir_relative,
		changed.changed, changed.new)
#######################
	status_check.check(check_ebuild_notadded, checkdir, checkdir_relative, xpkg)
	eadded.extend(status_check.eadded)

#################
	fetchcheck.check(xpkg, checkdir, checkdir_relative, changed.changed, changed.new)
#################

	if check_changelog and "ChangeLog" not in checkdirlist:
		qatracker.add_error("changelog.missing", xpkg + "/ChangeLog")
#################
	pkgmeta.check(xpkg, checkdir, checkdirlist, repolevel)
	muselist = frozenset(pkgmeta.musedict)
#################

	changelog_path = os.path.join(checkdir_relative, "ChangeLog")
	changelog_modified = changelog_path in changed.changelogs

	# detect unused local USE-descriptions
	used_useflags = set()

	for y_ebuild in ebuildlist:
##################
		ebuild = Ebuild(repo_settings, repolevel, pkgdir, catdir, vcs_settings, xpkg, y_ebuild)
##################

		if check_changelog and not changelog_modified \
			and ebuild.ebuild_path in changed.new_ebuilds:
			qatracker.add_error('changelog.ebuildadded', ebuild.relative_path)

		if ebuild.untracked(check_ebuild_notadded, y_ebuild, eadded):
			# ebuild not added to vcs
			qatracker.add_error("ebuild.notadded",
				xpkg + "/" + y_ebuild + ".ebuild")

##################
		if bad_split_check(xpkg, y_ebuild, pkgdir, qatracker):
			continue
###################
		pkg = pkgs[y_ebuild]
		if pkg_invalid(pkg, qatracker, ebuild):
			allvalid = False
			continue

		myaux = pkg._metadata
		eapi = myaux["EAPI"]
		inherited = pkg.inherited
		live_ebuild = live_eclasses.intersection(inherited)

		if repo_settings.repo_config.eapi_is_banned(eapi):
			qatracker.add_error("repo.eapi.banned",
				"%s: %s" % (ebuild.relative_path, eapi))

		elif repo_settings.repo_config.eapi_is_deprecated(eapi):
			qatracker.add_error("repo.eapi.deprecated",
				"%s: %s" % (ebuild.relative_path, eapi))

		for k, v in myaux.items():
			if not isinstance(v, basestring):
				continue
			m = non_ascii_re.search(v)
			if m is not None:
				qatracker.add_error("variable.invalidchar",
					"%s: %s variable contains non-ASCII "
					"character at position %s" %
					(ebuild.relative_path, k, m.start() + 1))

		if not fetchcheck.src_uri_error:
			#######################
			thirdparty.check(myaux, ebuild.relative_path)
			#######################
		if myaux.get("PROVIDE"):
			qatracker.add_error("virtual.oldstyle", ebuild.relative_path)

		for pos, missing_var in enumerate(missingvars):
			if not myaux.get(missing_var):
				if catdir == "virtual" and \
					missing_var in ("HOMEPAGE", "LICENSE"):
					continue
				if live_ebuild and missing_var == "KEYWORDS":
					continue
				myqakey = missingvars[pos] + ".missing"
				qatracker.add_error(myqakey, xpkg + "/" + y_ebuild + ".ebuild")

		if catdir == "virtual":
			for var in ("HOMEPAGE", "LICENSE"):
				if myaux.get(var):
					myqakey = var + ".virtual"
					qatracker.add_error(myqakey, ebuild.relative_path)

		# 14 is the length of DESCRIPTION=""
		if len(myaux['DESCRIPTION']) > max_desc_len:
			qatracker.add_error('DESCRIPTION.toolong',
				"%s: DESCRIPTION is %d characters (max %d)" %
				(ebuild.relative_path, len(myaux['DESCRIPTION']), max_desc_len))

		keywords = myaux["KEYWORDS"].split()

		ebuild_archs = set(
			kw.lstrip("~") for kw in keywords if not kw.startswith("-"))

		#######################
		keywordcheck.check(
			pkg, xpkg, ebuild, y_ebuild, keywords, ebuild_archs, changed,
			live_ebuild)
		#######################

		# KEYWORDS="-*" is a stupid replacement for package.mask
		# and screws general KEYWORDS semantics
		if "-*" in keywords:
			haskeyword = False
			for kw in keywords:
				if kw[0] == "~":
					kw = kw[1:]
				if kw in kwlist:
					haskeyword = True
			if not haskeyword:
				qatracker.add_error("KEYWORDS.stupid",
					xpkg + "/" + y_ebuild + ".ebuild")

		if live_ebuild and repo_settings.repo_config.name == "gentoo":
			#######################
			liveeclasscheck.check(
				pkg, xpkg, ebuild, y_ebuild, keywords, global_pmaskdict)
			#######################

		if options.ignore_arches:
			arches = [[
				repoman_settings["ARCH"], repoman_settings["ARCH"],
				repoman_settings["ACCEPT_KEYWORDS"].split()]]
		else:
			arches = set()
			for keyword in keywords:
				if keyword[0] == "-":
					continue
				elif keyword[0] == "~":
					arch = keyword[1:]
					if arch == "*":
						for expanded_arch in profiles:
							if expanded_arch == "**":
								continue
							arches.add(
								(keyword, expanded_arch, (
									expanded_arch, "~" + expanded_arch)))
					else:
						arches.add((keyword, arch, (arch, keyword)))
				else:
					if keyword == "*":
						for expanded_arch in profiles:
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
		catpkg = catdir + "/" + y_ebuild

		inherited_java_eclass = "java-pkg-2" in inherited or \
			"java-pkg-opt-2" in inherited
		inherited_wxwidgets_eclass = "wxwidgets" in inherited
		operator_tokens = set(["||", "(", ")"])
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
					qatracker.add_error(mytype + '.suspect',
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
						not portdb.xmatch("match-all", atom.without_use) and \
						not atom.cp.startswith("virtual/"):
						unknown_pkgs.add((mytype, atom.unevaluated_atom))

					if catdir != "virtual":
						if not is_blocker and \
							atom.cp in suspect_virtual:
							qatracker.add_error('virtual.suspect',
								ebuild.relative_path +
								": %s: consider using '%s' instead of '%s'" %
								(mytype, suspect_virtual[atom.cp], atom))
						if not is_blocker and \
							atom.cp.startswith("perl-core/"):
							qatracker.add_error('dependency.perlcore',
								ebuild.relative_path +
								": %s: please use '%s' instead of '%s'" %
								(mytype, atom.replace("perl-core/","virtual/perl-"), atom))

					if buildtime and \
						not is_blocker and \
						not inherited_java_eclass and \
						atom.cp == "virtual/jdk":
						qatracker.add_error('java.eclassesnotused',
							ebuild.relative_path)
					elif buildtime and \
						not is_blocker and \
						not inherited_wxwidgets_eclass and \
						atom.cp == "x11-libs/wxGTK":
						qatracker.add_error('wxwidgets.eclassnotused',
							"%s: %ss on x11-libs/wxGTK without inheriting"
							" wxwidgets.eclass" % (ebuild.relative_path, mytype))
					elif runtime:
						if not is_blocker and \
							atom.cp in suspect_rdepend:
							qatracker.add_error(mytype + '.suspect',
								ebuild.relative_path + ": '%s'" % atom)

					if atom.operator == "~" and \
						portage.versions.catpkgsplit(atom.cpv)[3] != "r0":
						qacat = 'dependency.badtilde'
						qatracker.add_error(qacat,
							"%s: %s uses the ~ operator"
							" with a non-zero revision: '%s'" %
							(ebuild.relative_path, mytype, atom))

					check_missingslot(atom, mytype, eapi, portdb, qatracker,
						ebuild.relative_path, myaux)

			type_list.extend([mytype] * (len(badsyntax) - len(type_list)))

		for m, b in zip(type_list, badsyntax):
			if m.endswith("DEPEND"):
				qacat = "dependency.syntax"
			else:
				qacat = m + ".syntax"
			qatracker.add_error(qacat,
				"%s: %s: %s" % (ebuild.relative_path, m, b))

		badlicsyntax = len([z for z in type_list if z == "LICENSE"])
		badprovsyntax = len([z for z in type_list if z == "PROVIDE"])
		baddepsyntax = len(type_list) != badlicsyntax + badprovsyntax
		badlicsyntax = badlicsyntax > 0
		badprovsyntax = badprovsyntax > 0

		#################
		use_flag_checks.check(pkg, xpkg, ebuild, y_ebuild, muselist)

		ebuild_used_useflags = use_flag_checks.getUsedUseFlags()
		used_useflags = used_useflags.union(ebuild_used_useflags)
		#################

		# Check for outdated RUBY targets
		old_ruby_eclasses = ["ruby-ng", "ruby-fakegem", "ruby"]
		is_old_ruby_eclass_inherited = filter(
			lambda e: e in inherited, old_ruby_eclasses)
		if is_old_ruby_eclass_inherited:
			ruby_intersection = pkg.iuse.all.intersection(ruby_deprecated)
			if ruby_intersection:
				for myruby in ruby_intersection:
					qatracker.add_error("IUSE.rubydeprecated",
						(ebuild.relative_path + ": Deprecated ruby target: %s")
						% myruby)

		# license checks
		if not badlicsyntax:
			# Parse the LICENSE variable, remove USE conditions and
			# flatten it.
			licenses = portage.dep.use_reduce(myaux["LICENSE"], matchall=1, flat=True)
			# Check each entry to ensure that it exists in PORTDIR's
			# license directory.
			for lic in licenses:
				# Need to check for "||" manually as no portage
				# function will remove it without removing values.
				if lic not in liclist and lic != "||":
					qatracker.add_error("LICENSE.invalid",
						xpkg + "/" + y_ebuild + ".ebuild: %s" % lic)
				elif lic in liclist_deprecated:
					qatracker.add_error("LICENSE.deprecated",
						"%s: %s" % (ebuild.relative_path, lic))

		# keyword checks
		myuse = myaux["KEYWORDS"].split()
		for mykey in myuse:
			if mykey not in ("-*", "*", "~*"):
				myskey = mykey
				if myskey[:1] == "-":
					myskey = myskey[1:]
				if myskey[:1] == "~":
					myskey = myskey[1:]
				if myskey not in kwlist:
					qatracker.add_error("KEYWORDS.invalid",
						"%s/%s.ebuild: %s" % (xpkg, y_ebuild, mykey))
				elif myskey not in profiles:
					qatracker.add_error("KEYWORDS.invalid",
						"%s/%s.ebuild: %s (profile invalid)"
						% (xpkg, y_ebuild, mykey))

		# restrict checks
		myrestrict = None
		try:
			myrestrict = portage.dep.use_reduce(
				myaux["RESTRICT"], matchall=1, flat=True)
		except portage.exception.InvalidDependString as e:
			qatracker.add_error("RESTRICT.syntax",
				"%s: RESTRICT: %s" % (ebuild.relative_path, e))
			del e
		if myrestrict:
			myrestrict = set(myrestrict)
			mybadrestrict = myrestrict.difference(valid_restrict)
			if mybadrestrict:
				for mybad in mybadrestrict:
					qatracker.add_error("RESTRICT.invalid",
						xpkg + "/" + y_ebuild + ".ebuild: %s" % mybad)

		# Syntax Checks

		if not vcs_settings.vcs_preserves_mtime:
			if ebuild.ebuild_path not in changed.new_ebuilds and \
				ebuild.ebuild_path not in changed.ebuilds:
				pkg.mtime = None
		try:
			# All ebuilds should have utf_8 encoding.
			f = io.open(
				_unicode_encode(
					ebuild.full_path, encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'])
			try:
				for check_name, e in run_checks(f, pkg):
					qatracker.add_error(check_name,
						ebuild.relative_path + ': %s' % e)
			finally:
				f.close()
		except UnicodeDecodeError:
			# A file.UTF8 failure will have already been recorded above.
			pass

		if options.force:
			# The dep_check() calls are the most expensive QA test. If --force
			# is enabled, there's no point in wasting time on these since the
			# user is intent on forcing the commit anyway.
			continue

		relevant_profiles = []
		for keyword, arch, groups in arches:
			if arch not in profiles:
				# A missing profile will create an error further down
				# during the KEYWORDS verification.
				continue

			if include_arches is not None:
				if arch not in include_arches:
					continue

			relevant_profiles.extend(
				(keyword, groups, prof) for prof in profiles[arch])

		def sort_key(item):
			return item[2].sub_path

		relevant_profiles.sort(key=sort_key)

		for keyword, groups, prof in relevant_profiles:

			is_stable_profile = prof.status == "stable"
			is_dev_profile = prof.status == "dev" and \
				options.include_dev
			is_exp_profile = prof.status == "exp" and \
				options.include_exp_profiles == 'y'
			if not (is_stable_profile or is_dev_profile or is_exp_profile):
				continue

			dep_settings = arch_caches.get(prof.sub_path)
			if dep_settings is None:
				dep_settings = portage.config(
					config_profile_path=prof.abs_path,
					config_incrementals=repoman_incrementals,
					config_root=config_root,
					local_config=False,
					_unmatched_removal=options.unmatched_removal,
					env=env, repositories=repoman_settings.repositories)
				dep_settings.categories = repoman_settings.categories
				if options.without_mask:
					dep_settings._mask_manager_obj = \
						copy.deepcopy(dep_settings._mask_manager)
					dep_settings._mask_manager._pmaskdict.clear()
				arch_caches[prof.sub_path] = dep_settings

			xmatch_cache_key = (prof.sub_path, tuple(groups))
			xcache = arch_xmatch_caches.get(xmatch_cache_key)
			if xcache is None:
				portdb.melt()
				portdb.freeze()
				xcache = portdb.xcache
				xcache.update(shared_xmatch_caches)
				arch_xmatch_caches[xmatch_cache_key] = xcache

			repo_settings.trees[repo_settings.root]["porttree"].settings = dep_settings
			portdb.settings = dep_settings
			portdb.xcache = xcache

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
					pkg.cpv not in portdb.xmatch("match-visible",
					Atom("%s::%s" % (pkg.cp, repo_settings.repo_config.name)))
				if ismasked:
					if not have_pmasked:
						have_pmasked = bool(dep_settings._getMaskAtom(
							pkg.cpv, pkg._metadata))
					if options.ignore_masked:
						continue
					# we are testing deps for a masked package; give it some lee-way
					suffix = "masked"
					matchmode = "minimum-all"
				else:
					suffix = ""
					matchmode = "minimum-visible"

				if not have_dev_keywords:
					have_dev_keywords = \
						bool(dev_keywords.intersection(keywords))

				if prof.status == "dev":
					suffix = suffix + "indev"

				for mytype in Package._dep_keys:

					mykey = "dependency.bad" + suffix
					myvalue = myaux[mytype]
					if not myvalue:
						continue

					success, atoms = portage.dep_check(
						myvalue, portdb, dep_settings,
						use="all", mode=matchmode, trees=repo_settings.trees)

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
										and not portdb.cp_list(atom.cp))]

							# we have some unsolvable deps
							# remove ! deps, which always show up as unsatisfiable
							atoms = [
								str(atom.unevaluated_atom)
								for atom in atoms if not atom.blocker]

							# if we emptied out our list, continue:
							if not atoms:
								continue
							qatracker.add_error(mykey,
								"%s: %s: %s(%s)\n%s"
								% (ebuild.relative_path, mytype, keyword, prof,
									pformat(atoms, indent=6)))
					else:
						qatracker.add_error(mykey,
							"%s: %s: %s(%s)\n%s"
							% (ebuild.relative_path, mytype, keyword, prof,
								pformat(atoms, indent=6)))

		if not baddepsyntax and unknown_pkgs:
			type_map = {}
			for mytype, atom in unknown_pkgs:
				type_map.setdefault(mytype, set()).add(atom)
			for mytype, atoms in type_map.items():
				qatracker.add_error("dependency.unknown",
					"%s: %s: %s"
					% (ebuild.relative_path, mytype, ", ".join(sorted(atoms))))

	# check if there are unused local USE-descriptions in metadata.xml
	# (unless there are any invalids, to avoid noise)
	if allvalid:
		for myflag in muselist.difference(used_useflags):
			qatracker.add_error("metadata.warning",
				"%s/metadata.xml: unused local USE-description: '%s'"
				% (xpkg, myflag))

if options.if_modified == "y" and len(effective_scanlist) < 1:
	logging.warning("--if-modified is enabled, but no modified packages were found!")

if options.mode == "manifest":
	sys.exit(dofail)

# dofail will be true if we have failed in at least one non-warning category
dofail = 0
# dowarn will be true if we tripped any warnings
dowarn = 0
# dofull will be true if we should print a "repoman full" informational message
dofull = options.mode != 'full'

for x in qacats:
	if x not in qatracker.fails:
		continue
	dowarn = 1
	if x not in qawarnings:
		dofail = 1

if dofail or \
	(dowarn and not (options.quiet or options.mode == "scan")):
	dofull = 0

# Save QA output so that it can be conveniently displayed
# in $EDITOR while the user creates a commit message.
# Otherwise, the user would not be able to see this output
# once the editor has taken over the screen.
qa_output = io.StringIO()
style_file = ConsoleStyleFile(sys.stdout)
if options.mode == 'commit' and \
	(not commitmessage or not commitmessage.strip()):
	style_file.write_listener = qa_output
console_writer = StyleWriter(file=style_file, maxcol=9999)
console_writer.style_listener = style_file.new_styles

f = formatter.AbstractFormatter(console_writer)

format_outputs = {
	'column': format_qa_output_column,
	'default': format_qa_output
}

format_output = format_outputs.get(
	options.output_style, format_outputs['default'])
format_output(f, qatracker.fails, dofull, dofail, options, qawarnings)

style_file.flush()
del console_writer, f, style_file
qa_output = qa_output.getvalue()
qa_output = qa_output.splitlines(True)

suggest_ignore_masked = False
suggest_include_dev = False

if have_pmasked and not (options.without_mask or options.ignore_masked):
	suggest_ignore_masked = True
if have_dev_keywords and not options.include_dev:
	suggest_include_dev = True

if suggest_ignore_masked or suggest_include_dev:
	print()
	if suggest_ignore_masked:
		print(bold(
			"Note: use --without-mask to check "
			"KEYWORDS on dependencies of masked packages"))

	if suggest_include_dev:
		print(bold(
			"Note: use --include-dev (-d) to check "
			"dependencies for 'dev' profiles"))
	print()

if options.mode != 'commit':
	if dofull:
		print(bold("Note: type \"repoman full\" for a complete listing."))
	if dowarn and not dofail:
		utilities.repoman_sez(
			"\"You're only giving me a partial QA payment?\n"
			"              I'll take it this time, but I'm not happy.\"")
	elif not dofail:
		utilities.repoman_sez(
			"\"If everyone were like you, I'd be out of business!\"")
	elif dofail:
		print(bad("Please fix these important QA issues first."))
		utilities.repoman_sez(
			"\"Make your QA payment on time"
			" and you'll never see the likes of me.\"\n")
		sys.exit(1)
else:
	if dofail and can_force and options.force and not options.pretend:
		utilities.repoman_sez(
			" \"You want to commit even with these QA issues?\n"
			"              I'll take it this time, but I'm not happy.\"\n")
	elif dofail:
		if options.force and not can_force:
			print(bad(
				"The --force option has been disabled"
				" due to extraordinary issues."))
		print(bad("Please fix these important QA issues first."))
		utilities.repoman_sez(
			"\"Make your QA payment on time"
			" and you'll never see the likes of me.\"\n")
		sys.exit(1)

	if options.pretend:
		utilities.repoman_sez(
			"\"So, you want to play it safe. Good call.\"\n")

	myunadded = []
	if vcs_settings.vcs == "cvs":
		try:
			myvcstree = portage.cvstree.getentries("./", recursive=1)
			myunadded = portage.cvstree.findunadded(
				myvcstree, recursive=1, basedir="./")
		except SystemExit as e:
			raise  # TODO propagate this
		except:
			err("Error retrieving CVS tree; exiting.")
	if vcs_settings.vcs == "svn":
		try:
			with repoman_popen("svn status --no-ignore") as f:
				svnstatus = f.readlines()
			myunadded = [
				"./" + elem.rstrip().split()[1]
				for elem in svnstatus
				if elem.startswith("?") or elem.startswith("I")]
		except SystemExit as e:
			raise  # TODO propagate this
		except:
			err("Error retrieving SVN info; exiting.")
	if vcs_settings.vcs == "git":
		# get list of files not under version control or missing
		myf = repoman_popen("git ls-files --others")
		myunadded = ["./" + elem[:-1] for elem in myf]
		myf.close()
	if vcs_settings.vcs == "bzr":
		try:
			with repoman_popen("bzr status -S .") as f:
				bzrstatus = f.readlines()
			myunadded = [
				"./" + elem.rstrip().split()[1].split('/')[-1:][0]
				for elem in bzrstatus
				if elem.startswith("?") or elem[0:2] == " D"]
		except SystemExit as e:
			raise  # TODO propagate this
		except:
			err("Error retrieving bzr info; exiting.")
	if vcs_settings.vcs == "hg":
		with repoman_popen("hg status --no-status --unknown .") as f:
			myunadded = f.readlines()
		myunadded = ["./" + elem.rstrip() for elem in myunadded]

		# Mercurial doesn't handle manually deleted files as removed from
		# the repository, so the user need to remove them before commit,
		# using "hg remove [FILES]"
		with repoman_popen("hg status --no-status --deleted .") as f:
			mydeleted = f.readlines()
		mydeleted = ["./" + elem.rstrip() for elem in mydeleted]

	myautoadd = []
	if myunadded:
		for x in range(len(myunadded) - 1, -1, -1):
			xs = myunadded[x].split("/")
			if repo_settings.repo_config.find_invalid_path_char(myunadded[x]) != -1:
				# The Manifest excludes this file,
				# so it's safe to ignore.
				del myunadded[x]
			elif xs[-1] == "files":
				print("!!! files dir is not added! Please correct this.")
				sys.exit(-1)
			elif xs[-1] == "Manifest":
				# It's a manifest... auto add
				myautoadd += [myunadded[x]]
				del myunadded[x]

	if myunadded:
		print(red(
			"!!! The following files are in your local tree"
			" but are not added to the master"))
		print(red(
			"!!! tree. Please remove them from the local tree"
			" or add them to the master tree."))
		for x in myunadded:
			print("   ", x)
		print()
		print()
		sys.exit(1)

	if vcs_settings.vcs == "hg" and mydeleted:
		print(red(
			"!!! The following files are removed manually"
			" from your local tree but are not"))
		print(red(
			"!!! removed from the repository."
			" Please remove them, using \"hg remove [FILES]\"."))
		for x in mydeleted:
			print("   ", x)
		print()
		print()
		sys.exit(1)

	if vcs_settings.vcs == "cvs":
		mycvstree = cvstree.getentries("./", recursive=1)
		mychanged = cvstree.findchanged(mycvstree, recursive=1, basedir="./")
		mynew = cvstree.findnew(mycvstree, recursive=1, basedir="./")
		myremoved = portage.cvstree.findremoved(mycvstree, recursive=1, basedir="./")
		bin_blob_pattern = re.compile("^-kb$")
		no_expansion = set(portage.cvstree.findoption(
			mycvstree, bin_blob_pattern, recursive=1, basedir="./"))

	if vcs_settings.vcs == "svn":
		with repoman_popen("svn status") as f:
			svnstatus = f.readlines()
		mychanged = [
			"./" + elem.split()[-1:][0]
			for elem in svnstatus
			if (elem[:1] in "MR" or elem[1:2] in "M")]
		mynew = [
			"./" + elem.split()[-1:][0]
			for elem in svnstatus
			if elem.startswith("A")]
		myremoved = [
			"./" + elem.split()[-1:][0]
			for elem in svnstatus
			if elem.startswith("D")]

		# Subversion expands keywords specified in svn:keywords properties.
		with repoman_popen("svn propget -R svn:keywords") as f:
			props = f.readlines()
		expansion = dict(
			("./" + prop.split(" - ")[0], prop.split(" - ")[1].split())
			for prop in props if " - " in prop)

	elif vcs_settings.vcs == "git":
		with repoman_popen(
			"git diff-index --name-only "
			"--relative --diff-filter=M HEAD") as f:
			mychanged = f.readlines()
		mychanged = ["./" + elem[:-1] for elem in mychanged]

		with repoman_popen(
			"git diff-index --name-only "
			"--relative --diff-filter=A HEAD") as f:
			mynew = f.readlines()
		mynew = ["./" + elem[:-1] for elem in mynew]

		with repoman_popen(
			"git diff-index --name-only "
			"--relative --diff-filter=D HEAD") as f:
			myremoved = f.readlines()
		myremoved = ["./" + elem[:-1] for elem in myremoved]

	if vcs_settings.vcs == "bzr":
		with repoman_popen("bzr status -S .") as f:
			bzrstatus = f.readlines()
		mychanged = [
			"./" + elem.split()[-1:][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem and elem[1:2] == "M"]
		mynew = [
			"./" + elem.split()[-1:][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem and (elem[1:2] in "NK" or elem[0:1] == "R")]
		myremoved = [
			"./" + elem.split()[-1:][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem.startswith("-")]
		myremoved = [
			"./" + elem.split()[-3:-2][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem and (elem[1:2] == "K" or elem[0:1] == "R")]
		# Bazaar expands nothing.

	if vcs_settings.vcs == "hg":
		with repoman_popen("hg status --no-status --modified .") as f:
			mychanged = f.readlines()
		mychanged = ["./" + elem.rstrip() for elem in mychanged]

		with repoman_popen("hg status --no-status --added .") as f:
			mynew = f.readlines()
		mynew = ["./" + elem.rstrip() for elem in mynew]

		with repoman_popen("hg status --no-status --removed .") as f:
			myremoved = f.readlines()
		myremoved = ["./" + elem.rstrip() for elem in myremoved]

	if vcs_settings.vcs:
		if not (mychanged or mynew or myremoved or (vcs_settings.vcs == "hg" and mydeleted)):
			utilities.repoman_sez(
				"\"Doing nothing is not always good for QA.\"")
			print()
			print("(Didn't find any changed files...)")
			print()
			sys.exit(1)

	# Manifests need to be regenerated after all other commits, so don't commit
	# them now even if they have changed.
	mymanifests = set()
	myupdates = set()
	for f in mychanged + mynew:
		if "Manifest" == os.path.basename(f):
			mymanifests.add(f)
		else:
			myupdates.add(f)
	myupdates.difference_update(myremoved)
	myupdates = list(myupdates)
	mymanifests = list(mymanifests)
	myheaders = []
	mydirty = []

	commitmessage = options.commitmsg
	if options.commitmsgfile:
		try:
			f = io.open(
				_unicode_encode(
					options.commitmsgfile,
					encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['content'], errors='replace')
			commitmessage = f.read()
			f.close()
			del f
		except (IOError, OSError) as e:
			if e.errno == errno.ENOENT:
				portage.writemsg(
					"!!! File Not Found:"
					" --commitmsgfile='%s'\n" % options.commitmsgfile)
			else:
				raise
		# We've read the content so the file is no longer needed.
		commitmessagefile = None
	if not commitmessage or not commitmessage.strip():
		msg_prefix = ""
		if repolevel > 1:
			msg_prefix = "/".join(reposplit[1:]) + ": "

		try:
			editor = os.environ.get("EDITOR")
			if editor and utilities.editor_is_executable(editor):
				commitmessage = utilities.get_commit_message_with_editor(
					editor, message=qa_output, prefix=msg_prefix)
			else:
				commitmessage = utilities.get_commit_message_with_stdin()
		except KeyboardInterrupt:
			logging.fatal("Interrupted; exiting...")
			sys.exit(1)
		if (not commitmessage or not commitmessage.strip()
				or commitmessage.strip() == msg_prefix):
			print("* no commit message?  aborting commit.")
			sys.exit(1)
	commitmessage = commitmessage.rstrip()
	changelog_msg = commitmessage
	portage_version = getattr(portage, "VERSION", None)
	gpg_key = repoman_settings.get("PORTAGE_GPG_KEY", "")
	dco_sob = repoman_settings.get("DCO_SIGNED_OFF_BY", "")
	if portage_version is None:
		sys.stderr.write("Failed to insert portage version in message!\n")
		sys.stderr.flush()
		portage_version = "Unknown"

	report_options = []
	if options.force:
		report_options.append("--force")
	if options.ignore_arches:
		report_options.append("--ignore-arches")
	if include_arches is not None:
		report_options.append(
			"--include-arches=\"%s\"" %
			" ".join(sorted(include_arches)))

	if vcs_settings.vcs == "git":
		# Use new footer only for git (see bug #438364).
		commit_footer = "\n\nPackage-Manager: portage-%s" % portage_version
		if report_options:
			commit_footer += "\nRepoMan-Options: " + " ".join(report_options)
		if repo_settings.sign_manifests:
			commit_footer += "\nManifest-Sign-Key: %s" % (gpg_key, )
		if dco_sob:
			commit_footer += "\nSigned-off-by: %s" % (dco_sob, )
	else:
		unameout = platform.system() + " "
		if platform.system() in ["Darwin", "SunOS"]:
			unameout += platform.processor()
		else:
			unameout += platform.machine()
		commit_footer = "\n\n"
		if dco_sob:
			commit_footer += "Signed-off-by: %s\n" % (dco_sob, )
		commit_footer += "(Portage version: %s/%s/%s" % \
			(portage_version, vcs_settings.vcs, unameout)
		if report_options:
			commit_footer += ", RepoMan options: " + " ".join(report_options)
		if repo_settings.sign_manifests:
			commit_footer += ", signed Manifest commit with key %s" % \
				(gpg_key, )
		else:
			commit_footer += ", unsigned Manifest commit"
		commit_footer += ")"

	commitmessage += commit_footer

	broken_changelog_manifests = []
	if options.echangelog in ('y', 'force'):
		logging.info("checking for unmodified ChangeLog files")
		committer_name = utilities.get_committer_name(env=repoman_settings)
		for x in sorted(vcs_files_to_cps(
			chain(myupdates, mymanifests, myremoved),
			repolevel, reposplit, categories)):
			catdir, pkgdir = x.split("/")
			checkdir = repo_settings.repodir + "/" + x
			checkdir_relative = ""
			if repolevel < 3:
				checkdir_relative = os.path.join(pkgdir, checkdir_relative)
			if repolevel < 2:
				checkdir_relative = os.path.join(catdir, checkdir_relative)
			checkdir_relative = os.path.join(".", checkdir_relative)

			changelog_path = os.path.join(checkdir_relative, "ChangeLog")
			changelog_modified = changelog_path in changed.changelogs
			if changelog_modified and options.echangelog != 'force':
				continue

			# get changes for this package
			cdrlen = len(checkdir_relative)
			check_relative = lambda e: e.startswith(checkdir_relative)
			split_relative = lambda e: e[cdrlen:]
			clnew = list(map(split_relative, filter(check_relative, mynew)))
			clremoved = list(map(split_relative, filter(check_relative, myremoved)))
			clchanged = list(map(split_relative, filter(check_relative, mychanged)))

			# Skip ChangeLog generation if only the Manifest was modified,
			# as discussed in bug #398009.
			nontrivial_cl_files = set()
			nontrivial_cl_files.update(clnew, clremoved, clchanged)
			nontrivial_cl_files.difference_update(['Manifest'])
			if not nontrivial_cl_files and options.echangelog != 'force':
				continue

			new_changelog = utilities.UpdateChangeLog(
				checkdir_relative, committer_name, changelog_msg,
				os.path.join(repo_settings.repodir, 'skel.ChangeLog'),
				catdir, pkgdir,
				new=clnew, removed=clremoved, changed=clchanged,
				pretend=options.pretend)
			if new_changelog is None:
				writemsg_level(
					"!!! Updating the ChangeLog failed\n",
					level=logging.ERROR, noiselevel=-1)
				sys.exit(1)

			# if the ChangeLog was just created, add it to vcs
			if new_changelog:
				myautoadd.append(changelog_path)
				# myautoadd is appended to myupdates below
			else:
				myupdates.append(changelog_path)

			if options.ask and not options.pretend:
				# regenerate Manifest for modified ChangeLog (bug #420735)
				repoman_settings["O"] = checkdir
				digestgen(mysettings=repoman_settings, myportdb=portdb)
			else:
				broken_changelog_manifests.append(x)

	if myautoadd:
		print(">>> Auto-Adding missing Manifest/ChangeLog file(s)...")
		add_cmd = [vcs_settings.vcs, "add"]
		add_cmd += myautoadd
		if options.pretend:
			portage.writemsg_stdout(
				"(%s)\n" % " ".join(add_cmd),
				noiselevel=-1)
		else:

			if sys.hexversion < 0x3020000 and sys.hexversion >= 0x3000000 and \
				not os.path.isabs(add_cmd[0]):
				# Python 3.1 _execvp throws TypeError for non-absolute executable
				# path passed as bytes (see http://bugs.python.org/issue8513).
				fullname = find_binary(add_cmd[0])
				if fullname is None:
					raise portage.exception.CommandNotFound(add_cmd[0])
				add_cmd[0] = fullname

			add_cmd = [_unicode_encode(arg) for arg in add_cmd]
			retcode = subprocess.call(add_cmd)
			if retcode != os.EX_OK:
				logging.error(
					"Exiting on %s error code: %s\n" % (vcs_settings.vcs, retcode))
				sys.exit(retcode)

		myupdates += myautoadd

	print("* %s files being committed..." % green(str(len(myupdates))), end=' ')

	if vcs_settings.vcs not in ('cvs', 'svn'):
		# With git, bzr and hg, there's never any keyword expansion, so
		# there's no need to regenerate manifests and all files will be
		# committed in one big commit at the end.
		print()
	elif not repo_settings.repo_config.thin_manifest:
		if vcs_settings.vcs == 'cvs':
			headerstring = "'\$(Header|Id).*\$'"
		elif vcs_settings.vcs == "svn":
			svn_keywords = dict((k.lower(), k) for k in [
				"Rev",
				"Revision",
				"LastChangedRevision",
				"Date",
				"LastChangedDate",
				"Author",
				"LastChangedBy",
				"URL",
				"HeadURL",
				"Id",
				"Header",
			])

		for myfile in myupdates:

			# for CVS, no_expansion contains files that are excluded from expansion
			if vcs_settings.vcs == "cvs":
				if myfile in no_expansion:
					continue

			# for SVN, expansion contains files that are included in expansion
			elif vcs_settings.vcs == "svn":
				if myfile not in expansion:
					continue

				# Subversion keywords are case-insensitive
				# in svn:keywords properties,
				# but case-sensitive in contents of files.
				enabled_keywords = []
				for k in expansion[myfile]:
					keyword = svn_keywords.get(k.lower())
					if keyword is not None:
						enabled_keywords.append(keyword)

				headerstring = "'\$(%s).*\$'" % "|".join(enabled_keywords)

			myout = repoman_getstatusoutput(
				"egrep -q %s %s" % (headerstring, portage._shell_quote(myfile)))
			if myout[0] == 0:
				myheaders.append(myfile)

		print("%s have headers that will change." % green(str(len(myheaders))))
		print(
			"* Files with headers will"
			" cause the manifests to be changed and committed separately.")

	logging.info("myupdates: %s", myupdates)
	logging.info("myheaders: %s", myheaders)

	uq = UserQuery(options)
	if options.ask and uq.query('Commit changes?', True) != 'Yes':
		print("* aborting commit.")
		sys.exit(128 + signal.SIGINT)

	# Handle the case where committed files have keywords which
	# will change and need a priming commit before the Manifest
	# can be committed.
	if (myupdates or myremoved) and myheaders:
		myfiles = myupdates + myremoved
		fd, commitmessagefile = tempfile.mkstemp(".repoman.msg")
		mymsg = os.fdopen(fd, "wb")
		mymsg.write(_unicode_encode(commitmessage))
		mymsg.close()

		separator = '-' * 78

		print()
		print(green("Using commit message:"))
		print(green(separator))
		print(commitmessage)
		print(green(separator))
		print()

		# Having a leading ./ prefix on file paths can trigger a bug in
		# the cvs server when committing files to multiple directories,
		# so strip the prefix.
		myfiles = [f.lstrip("./") for f in myfiles]

		commit_cmd = [vcs_settings.vcs]
		commit_cmd.extend(vcs_settings.vcs_global_opts)
		commit_cmd.append("commit")
		commit_cmd.extend(vcs_settings.vcs_local_opts)
		commit_cmd.extend(["-F", commitmessagefile])
		commit_cmd.extend(myfiles)

		try:
			if options.pretend:
				print("(%s)" % (" ".join(commit_cmd),))
			else:
				retval = spawn(commit_cmd, env=repo_settings.commit_env)
				if retval != os.EX_OK:
					writemsg_level(
						"!!! Exiting on %s (shell) "
						"error code: %s\n" % (vcs_settings.vcs, retval),
						level=logging.ERROR, noiselevel=-1)
					sys.exit(retval)
		finally:
			try:
				os.unlink(commitmessagefile)
			except OSError:
				pass

	# Setup the GPG commands
	def gpgsign(filename):
		gpgcmd = repoman_settings.get("PORTAGE_GPG_SIGNING_COMMAND")
		if gpgcmd in [None, '']:
			raise MissingParameter("PORTAGE_GPG_SIGNING_COMMAND is unset!"
				" Is make.globals missing?")
		if "${PORTAGE_GPG_KEY}" in gpgcmd and \
			"PORTAGE_GPG_KEY" not in repoman_settings:
			raise MissingParameter("PORTAGE_GPG_KEY is unset!")
		if "${PORTAGE_GPG_DIR}" in gpgcmd:
			if "PORTAGE_GPG_DIR" not in repoman_settings:
				repoman_settings["PORTAGE_GPG_DIR"] = \
					os.path.expanduser("~/.gnupg")
				logging.info(
					"Automatically setting PORTAGE_GPG_DIR to '%s'" %
					repoman_settings["PORTAGE_GPG_DIR"])
			else:
				repoman_settings["PORTAGE_GPG_DIR"] = \
					os.path.expanduser(repoman_settings["PORTAGE_GPG_DIR"])
			if not os.access(repoman_settings["PORTAGE_GPG_DIR"], os.X_OK):
				raise portage.exception.InvalidLocation(
					"Unable to access directory: PORTAGE_GPG_DIR='%s'" %
					repoman_settings["PORTAGE_GPG_DIR"])
		gpgvars = {"FILE": filename}
		for k in ("PORTAGE_GPG_DIR", "PORTAGE_GPG_KEY"):
			v = repoman_settings.get(k)
			if v is not None:
				gpgvars[k] = v
		gpgcmd = portage.util.varexpand(gpgcmd, mydict=gpgvars)
		if options.pretend:
			print("(" + gpgcmd + ")")
		else:
			# Encode unicode manually for bug #310789.
			gpgcmd = portage.util.shlex_split(gpgcmd)

			if sys.hexversion < 0x3020000 and sys.hexversion >= 0x3000000 and \
				not os.path.isabs(gpgcmd[0]):
				# Python 3.1 _execvp throws TypeError for non-absolute executable
				# path passed as bytes (see http://bugs.python.org/issue8513).
				fullname = find_binary(gpgcmd[0])
				if fullname is None:
					raise portage.exception.CommandNotFound(gpgcmd[0])
				gpgcmd[0] = fullname

			gpgcmd = [
				_unicode_encode(arg, encoding=_encodings['fs'], errors='strict')
				for arg in gpgcmd]
			rValue = subprocess.call(gpgcmd)
			if rValue == os.EX_OK:
				os.rename(filename + ".asc", filename)
			else:
				raise portage.exception.PortageException(
					"!!! gpg exited with '" + str(rValue) + "' status")

	def need_signature(filename):
		try:
			with open(
				_unicode_encode(
					filename, encoding=_encodings['fs'], errors='strict'),
				'rb') as f:
				return b"BEGIN PGP SIGNED MESSAGE" not in f.readline()
		except IOError as e:
			if e.errno in (errno.ENOENT, errno.ESTALE):
				return False
			raise

	# When files are removed and re-added, the cvs server will put /Attic/
	# inside the $Header path. This code detects the problem and corrects it
	# so that the Manifest will generate correctly. See bug #169500.
	# Use binary mode in order to avoid potential character encoding issues.
	cvs_header_re = re.compile(br'^#\s*\$Header.*\$$')
	attic_str = b'/Attic/'
	attic_replace = b'/'
	for x in myheaders:
		f = open(
			_unicode_encode(x, encoding=_encodings['fs'], errors='strict'),
			mode='rb')
		mylines = f.readlines()
		f.close()
		modified = False
		for i, line in enumerate(mylines):
			if cvs_header_re.match(line) is not None and \
				attic_str in line:
				mylines[i] = line.replace(attic_str, attic_replace)
				modified = True
		if modified:
			portage.util.write_atomic(x, b''.join(mylines), mode='wb')

	if repolevel == 1:
		utilities.repoman_sez(
			"\"You're rather crazy... "
			"doing the entire repository.\"\n")

	if vcs_settings.vcs in ('cvs', 'svn') and (myupdates or myremoved):
		for x in sorted(vcs_files_to_cps(
			chain(myupdates, myremoved, mymanifests),
			repolevel, reposplit, categories)):
			repoman_settings["O"] = os.path.join(repo_settings.repodir, x)
			digestgen(mysettings=repoman_settings, myportdb=portdb)

	elif broken_changelog_manifests:
		for x in broken_changelog_manifests:
			repoman_settings["O"] = os.path.join(repo_settings.repodir, x)
			digestgen(mysettings=repoman_settings, myportdb=portdb)

	signed = False
	if repo_settings.sign_manifests:
		signed = True
		try:
			for x in sorted(vcs_files_to_cps(
				chain(myupdates, myremoved, mymanifests),
				repolevel, reposplit, categories)):
				repoman_settings["O"] = os.path.join(repo_settings.repodir, x)
				manifest_path = os.path.join(repoman_settings["O"], "Manifest")
				if not need_signature(manifest_path):
					continue
				gpgsign(manifest_path)
		except portage.exception.PortageException as e:
			portage.writemsg("!!! %s\n" % str(e))
			portage.writemsg("!!! Disabled FEATURES='sign'\n")
			signed = False

	if vcs_settings.vcs == 'git':
		# It's not safe to use the git commit -a option since there might
		# be some modified files elsewhere in the working tree that the
		# user doesn't want to commit. Therefore, call git update-index
		# in order to ensure that the index is updated with the latest
		# versions of all new and modified files in the relevant portion
		# of the working tree.
		myfiles = mymanifests + myupdates
		myfiles.sort()
		update_index_cmd = ["git", "update-index"]
		update_index_cmd.extend(f.lstrip("./") for f in myfiles)
		if options.pretend:
			print("(%s)" % (" ".join(update_index_cmd),))
		else:
			retval = spawn(update_index_cmd, env=os.environ)
			if retval != os.EX_OK:
				writemsg_level(
					"!!! Exiting on %s (shell) "
					"error code: %s\n" % (vcs_settings.vcs, retval),
					level=logging.ERROR, noiselevel=-1)
				sys.exit(retval)

	if True:
		myfiles = mymanifests[:]
		# If there are no header (SVN/CVS keywords) changes in
		# the files, this Manifest commit must include the
		# other (yet uncommitted) files.
		if not myheaders:
			myfiles += myupdates
			myfiles += myremoved
		myfiles.sort()

		fd, commitmessagefile = tempfile.mkstemp(".repoman.msg")
		mymsg = os.fdopen(fd, "wb")
		mymsg.write(_unicode_encode(commitmessage))
		mymsg.close()

		commit_cmd = []
		if options.pretend and vcs_settings.vcs is None:
			# substitute a bogus value for pretend output
			commit_cmd.append("cvs")
		else:
			commit_cmd.append(vcs_settings.vcs)
		commit_cmd.extend(vcs_settings.vcs_global_opts)
		commit_cmd.append("commit")
		commit_cmd.extend(vcs_settings.vcs_local_opts)
		if vcs_settings.vcs == "hg":
			commit_cmd.extend(["--logfile", commitmessagefile])
			commit_cmd.extend(myfiles)
		else:
			commit_cmd.extend(["-F", commitmessagefile])
			commit_cmd.extend(f.lstrip("./") for f in myfiles)

		try:
			if options.pretend:
				print("(%s)" % (" ".join(commit_cmd),))
			else:
				retval = spawn(commit_cmd, env=repo_settings.commit_env)
				if retval != os.EX_OK:
					if repo_settings.repo_config.sign_commit and vcs_settings.vcs == 'git' and \
						not git_supports_gpg_sign():
						# Inform user that newer git is needed (bug #403323).
						logging.error(
							"Git >=1.7.9 is required for signed commits!")

					writemsg_level(
						"!!! Exiting on %s (shell) "
						"error code: %s\n" % (vcs_settings.vcs, retval),
						level=logging.ERROR, noiselevel=-1)
					sys.exit(retval)
		finally:
			try:
				os.unlink(commitmessagefile)
			except OSError:
				pass

	print()
	if vcs_settings.vcs:
		print("Commit complete.")
	else:
		print(
			"repoman was too scared"
			" by not seeing any familiar version control file"
			" that he forgot to commit anything")
	utilities.repoman_sez(
		"\"If everyone were like you, I'd be out of business!\"\n")
sys.exit(0)
