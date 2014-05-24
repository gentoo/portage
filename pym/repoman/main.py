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
import stat
import subprocess
import sys
import tempfile
import textwrap
import platform
from itertools import chain
from stat import S_ISDIR
from pprint import pformat

from os import path as osp
if osp.isfile(osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), ".portage_not_installed")):
	sys.path.insert(0, osp.join(osp.dirname(osp.dirname(osp.realpath(__file__))), "pym"))
import portage
portage._internal_caller = True
portage._disable_legacy_globals()

try:
	import xml.etree.ElementTree
	from xml.parsers.expat import ExpatError
except (SystemExit, KeyboardInterrupt):
	raise
except (ImportError, SystemError, RuntimeError, Exception):
	# broken or missing xml support
	# http://bugs.python.org/issue14988
	msg = ["Please enable python's \"xml\" USE flag in order to use repoman."]
	from portage.output import EOutput
	out = EOutput()
	for line in msg:
		out.eerror(line)
	sys.exit(1)

from portage import os
from portage import _encodings
from portage import _unicode_encode
import portage.util.formatter as formatter
import repoman.argparser
from repoman.argparser import parse_args
from repoman import utilities
from _emerge.Package import Package
from _emerge.RootConfig import RootConfig
from _emerge.UserQuery import UserQuery
import portage.checksum
import portage.const
import portage.repository.config
from portage import cvstree, normalize_path
from portage import util
from portage.exception import (
	FileNotFound, InvalidAtom, MissingParameter, ParseError, PermissionDenied)
from portage.dep import Atom
from portage.process import find_binary, spawn
from portage.output import (
	bold, create_color_func, green, nocolor, red)
from portage.output import ConsoleStyleFile, StyleWriter
from portage.util import writemsg_level
from portage.package.ebuild.digestgen import digestgen
from portage.eapi import eapi_has_iuse_defaults, eapi_has_required_use

from repoman.checks.ebuilds import run_checks, checks_init
from repoman.checks.herds.herdbase import make_herd_base
from repoman.check_missingslot import check_missingslot
from repoman.metadata import (fetch_metadata_dtd, metadata_xml_encoding,
	metadata_doctype_name, metadata_xml_declaration)
from repoman.profile import dev_keywords, ProfileDesc, valid_profile_types
from repoman.qa_data import (qahelp, qawarnings, qacats, no_exec, allvars,
	max_desc_len, missingvars, suspect_virtual, suspect_rdepend, valid_restrict)
from repoman.subprocess import repoman_popen, repoman_getstatusoutput
from repoman.vcs import (vcs_files_to_cps, vcs_new_changed,
	git_supports_gpg_sign, ruby_deprecated)
from repoman._xml import _XMLParser, _MetadataTreeBuilder, metadata_dtd_uri


if sys.hexversion >= 0x3000000:
	basestring = str

util.initialize_logger()

commitmessage = None

pv_toolong_re = re.compile(r'[0-9]{19,}')
GPG_KEY_ID_REGEX = r'(0x)?([0-9a-fA-F]{8}){1,5}!?'
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


def warn(txt):
	print("repoman: " + txt)


def err(txt):
	warn(txt)
	sys.exit(1)


def exithandler(signum=None, _frame=None):
	logging.fatal("Interrupted; exiting...")
	if signum is None:
		sys.exit(1)
	else:
		sys.exit(128 + signum)


signal.signal(signal.SIGINT, exithandler)

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

if options.vcs:
	if options.vcs in ('cvs', 'svn', 'git', 'bzr', 'hg'):
		vcs = options.vcs
	else:
		vcs = None
else:
	vcses = utilities.FindVCS()
	if len(vcses) > 1:
		print(red(
			'*** Ambiguous workdir -- more than one VCS found'
			' at the same depth: %s.' % ', '.join(vcses)))
		print(red(
			'*** Please either clean up your workdir'
			' or specify --vcs option.'))
		sys.exit(1)
	elif vcses:
		vcs = vcses[0]
	else:
		vcs = None

if options.if_modified == "y" and vcs is None:
	logging.info(
		"Not in a version controlled repository; "
		"disabling --if-modified.")
	options.if_modified = "n"

# Disable copyright/mtime check if vcs does not preserve mtime (bug #324075).
vcs_preserves_mtime = vcs in ('cvs', None)

vcs_local_opts = repoman_settings.get("REPOMAN_VCS_LOCAL_OPTS", "").split()
vcs_global_opts = repoman_settings.get("REPOMAN_VCS_GLOBAL_OPTS")
if vcs_global_opts is None:
	if vcs in ('cvs', 'svn'):
		vcs_global_opts = "-q"
	else:
		vcs_global_opts = ""
vcs_global_opts = vcs_global_opts.split()

if options.mode == 'commit' and not options.pretend and not vcs:
	logging.info("Not in a version controlled repository; enabling pretend mode.")
	options.pretend = True

# Ensure that current repository is in the list of enabled repositories.
repodir = os.path.realpath(portdir_overlay)
try:
	repoman_settings.repositories.get_repo_for_location(repodir)
except KeyError:
	repo_conf = portage.repository.config
	repo_name = repo_conf.RepoConfig._read_valid_repo_name(portdir_overlay)[0]
	layout_conf_data = repo_conf.parse_layout_conf(portdir_overlay)[0]
	if layout_conf_data['repo-name']:
		repo_name = layout_conf_data['repo-name']
	tmp_conf_file = io.StringIO(textwrap.dedent("""
		[%s]
		location = %s
		""") % (repo_name, portdir_overlay))
	# Ensure that the repository corresponding to $PWD overrides a
	# repository of the same name referenced by the existing PORTDIR
	# or PORTDIR_OVERLAY settings.
	repoman_settings['PORTDIR_OVERLAY'] = "%s %s" % (
		repoman_settings.get('PORTDIR_OVERLAY', ''),
		portage._shell_quote(portdir_overlay))
	repositories = repo_conf.load_repository_config(
		repoman_settings, extra_files=[tmp_conf_file])
	# We have to call the config constructor again so that attributes
	# dependent on config.repositories are initialized correctly.
	repoman_settings = portage.config(
		config_root=config_root, local_config=False, repositories=repositories)

root = repoman_settings['EROOT']
trees = {
	root: {'porttree': portage.portagetree(settings=repoman_settings)}
}
portdb = trees[root]['porttree'].dbapi

# Constrain dependency resolution to the master(s)
# that are specified in layout.conf.
repo_config = repoman_settings.repositories.get_repo_for_location(repodir)
portdb.porttrees = list(repo_config.eclass_db.porttrees)
portdir = portdb.porttrees[0]
commit_env = os.environ.copy()
# list() is for iteration on a copy.
for repo in list(repoman_settings.repositories):
	# all paths are canonical
	if repo.location not in repo_config.eclass_db.porttrees:
		del repoman_settings.repositories[repo.name]

if repo_config.allow_provide_virtual:
	qawarnings.add("virtual.oldstyle")

if repo_config.sign_commit:
	if vcs == 'git':
		# NOTE: It's possible to use --gpg-sign=key_id to specify the key in
		# the commit arguments. If key_id is unspecified, then it must be
		# configured by `git config user.signingkey key_id`.
		vcs_local_opts.append("--gpg-sign")
		if repoman_settings.get("PORTAGE_GPG_DIR"):
			# Pass GNUPGHOME to git for bug #462362.
			commit_env["GNUPGHOME"] = repoman_settings["PORTAGE_GPG_DIR"]

		# Pass GPG_TTY to git for bug #477728.
		try:
			commit_env["GPG_TTY"] = os.ttyname(sys.stdin.fileno())
		except OSError:
			pass

# In order to disable manifest signatures, repos may set
# "sign-manifests = false" in metadata/layout.conf. This
# can be used to prevent merge conflicts like those that
# thin-manifests is designed to prevent.
sign_manifests = "sign" in repoman_settings.features and \
	repo_config.sign_manifest

if repo_config.sign_manifest and repo_config.name == "gentoo" and \
	options.mode in ("commit",) and not sign_manifests:
	msg = (
		"The '%s' repository has manifest signatures enabled, "
		"but FEATURES=sign is currently disabled. In order to avoid this "
		"warning, enable FEATURES=sign in make.conf. Alternatively, "
		"repositories can disable manifest signatures by setting "
		"'sign-manifests = false' in metadata/layout.conf.") % (
			repo_config.name,)
	for line in textwrap.wrap(msg, 60):
		logging.warning(line)

is_commit = options.mode in ("commit",)
valid_gpg_key = repoman_settings.get("PORTAGE_GPG_KEY") and re.match(
	r'^%s$' % GPG_KEY_ID_REGEX, repoman_settings["PORTAGE_GPG_KEY"])

if sign_manifests and is_commit and not valid_gpg_key:
	logging.error(
		"PORTAGE_GPG_KEY value is invalid: %s" %
		repoman_settings["PORTAGE_GPG_KEY"])
	sys.exit(1)

manifest_hashes = repo_config.manifest_hashes
if manifest_hashes is None:
	manifest_hashes = portage.const.MANIFEST2_HASH_DEFAULTS

if options.mode in ("commit", "fix", "manifest"):
	if portage.const.MANIFEST2_REQUIRED_HASH not in manifest_hashes:
		msg = (
			"The 'manifest-hashes' setting in the '%s' repository's "
			"metadata/layout.conf does not contain the '%s' hash which "
			"is required by this portage version. You will have to "
			"upgrade portage if you want to generate valid manifests for "
			"this repository.") % (
			repo_config.name, portage.const.MANIFEST2_REQUIRED_HASH)
		for line in textwrap.wrap(msg, 70):
			logging.error(line)
		sys.exit(1)

	unsupported_hashes = manifest_hashes.difference(
		portage.const.MANIFEST2_HASH_FUNCTIONS)
	if unsupported_hashes:
		msg = (
			"The 'manifest-hashes' setting in the '%s' repository's "
			"metadata/layout.conf contains one or more hash types '%s' "
			"which are not supported by this portage version. You will "
			"have to upgrade portage if you want to generate valid "
			"manifests for this repository.") % (
			repo_config.name, " ".join(sorted(unsupported_hashes)))
		for line in textwrap.wrap(msg, 70):
			logging.error(line)
		sys.exit(1)

if options.echangelog is None and repo_config.update_changelog:
	options.echangelog = 'y'

if vcs is None:
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
vcs_is_cvs_or_svn = vcs in ('cvs', 'svn')
check_changelog = not is_echangelog_enabled and vcs_is_cvs_or_svn

if 'digest' in repoman_settings.features and options.digest != 'n':
	options.digest = 'y'

logging.debug("vcs: %s" % (vcs,))
logging.debug("repo config: %s" % (repo_config,))
logging.debug("options: %s" % (options,))

# It's confusing if these warnings are displayed without the user
# being told which profile they come from, so disable them.
env = os.environ.copy()
env['FEATURES'] = env.get('FEATURES', '') + ' -unknown-features-warn'

categories = []
for path in repo_config.eclass_db.porttrees:
	categories.extend(portage.util.grabfile(
		os.path.join(path, 'profiles', 'categories')))
repoman_settings.categories = frozenset(
	portage.util.stack_lists([categories], incremental=1))
categories = repoman_settings.categories

portdb.settings = repoman_settings
root_config = RootConfig(repoman_settings, trees[root], None)
# We really only need to cache the metadata that's necessary for visibility
# filtering. Anything else can be discarded to reduce memory consumption.
portdb._aux_cache_keys.clear()
portdb._aux_cache_keys.update(
	["EAPI", "IUSE", "KEYWORDS", "repository", "SLOT"])

reposplit = myreporoot.split(os.path.sep)
repolevel = len(reposplit)

# Check if it's in $PORTDIR/$CATEGORY/$PN , otherwise bail if commiting.
# Reason for this is if they're trying to commit in just $FILESDIR/*,
# the Manifest needs updating.
# This check ensures that repoman knows where it is,
# and the manifest recommit is at least possible.
if options.mode == 'commit' and repolevel not in [1, 2, 3]:
	print(red("***") + (
		" Commit attempts *must* be from within a vcs checkout,"
		" category, or package directory."))
	print(red("***") + (
		" Attempting to commit from a packages files directory"
		" will be blocked for instance."))
	print(red("***") + (
		" This is intended behaviour,"
		" to ensure the manifest is recommitted for a package."))
	print(red("***"))
	err(
		"Unable to identify level we're commiting from for %s" %
		'/'.join(reposplit))

# Make startdir relative to the canonical repodir, so that we can pass
# it to digestgen and it won't have to be canonicalized again.
if repolevel == 1:
	startdir = repodir
else:
	startdir = normalize_path(mydir)
	startdir = os.path.join(repodir, *startdir.split(os.sep)[-2 - repolevel + 3:])


def caterror(mycat):
	err(
		"%s is not an official category."
		"  Skipping QA checks in this directory.\n"
		"Please ensure that you add %s to %s/profiles/categories\n"
		"if it is a new category." % (mycat, catdir, repodir))


profile_list = []

# get lists of valid keywords, licenses, and use
kwlist = set()
liclist = set()
uselist = set()
global_pmasklines = []

for path in portdb.porttrees:
	try:
		liclist.update(os.listdir(os.path.join(path, "licenses")))
	except OSError:
		pass
	kwlist.update(
		portage.grabfile(os.path.join(path, "profiles", "arch.list")))

	use_desc = portage.grabfile(os.path.join(path, 'profiles', 'use.desc'))
	for x in use_desc:
		x = x.split()
		if x:
			uselist.add(x[0])

	expand_desc_dir = os.path.join(path, 'profiles', 'desc')
	try:
		expand_list = os.listdir(expand_desc_dir)
	except OSError:
		pass
	else:
		for fn in expand_list:
			if not fn[-5:] == '.desc':
				continue
			use_prefix = fn[:-5].lower() + '_'
			for x in portage.grabfile(os.path.join(expand_desc_dir, fn)):
				x = x.split()
				if x:
					uselist.add(use_prefix + x[0])

	global_pmasklines.append(
		portage.util.grabfile_package(
			os.path.join(path, 'profiles', 'package.mask'),
			recursive=1, verify_eapi=True))

	desc_path = os.path.join(path, 'profiles', 'profiles.desc')
	try:
		desc_file = io.open(
			_unicode_encode(
				desc_path, encoding=_encodings['fs'], errors='strict'),
			mode='r', encoding=_encodings['repo.content'], errors='replace')
	except EnvironmentError:
		pass
	else:
		for i, x in enumerate(desc_file):
			if x[0] == "#":
				continue
			arch = x.split()
			if len(arch) == 0:
				continue
			if len(arch) != 3:
				err(
					"wrong format: \"%s\" in %s line %d" %
					(bad(x.strip()), desc_path, i + 1, ))
			elif arch[0] not in kwlist:
				err(
					"invalid arch: \"%s\" in %s line %d" %
					(bad(arch[0]), desc_path, i + 1, ))
			elif arch[2] not in valid_profile_types:
				err(
					"invalid profile type: \"%s\" in %s line %d" %
					(bad(arch[2]), desc_path, i + 1, ))
			profile_desc = ProfileDesc(arch[0], arch[2], arch[1], path)
			if not os.path.isdir(profile_desc.abs_path):
				logging.error(
					"Invalid %s profile (%s) for arch %s in %s line %d",
					arch[2], arch[1], arch[0], desc_path, i + 1)
				continue
			if os.path.exists(
				os.path.join(profile_desc.abs_path, 'deprecated')):
				continue
			profile_list.append(profile_desc)
		desc_file.close()

repoman_settings['PORTAGE_ARCHLIST'] = ' '.join(sorted(kwlist))
repoman_settings.backup_changes('PORTAGE_ARCHLIST')

global_pmasklines = portage.util.stack_lists(global_pmasklines, incremental=1)
global_pmaskdict = {}
for x in global_pmasklines:
	global_pmaskdict.setdefault(x.cp, []).append(x)
del global_pmasklines


def has_global_mask(pkg):
	mask_atoms = global_pmaskdict.get(pkg.cp)
	if mask_atoms:
		pkg_list = [pkg]
		for x in mask_atoms:
			if portage.dep.match_from_list(x, pkg_list):
				return x
	return None


# Ensure that profile sub_path attributes are unique. Process in reverse order
# so that profiles with duplicate sub_path from overlays will override
# profiles with the same sub_path from parent repos.
profiles = {}
profile_list.reverse()
profile_sub_paths = set()
for prof in profile_list:
	if prof.sub_path in profile_sub_paths:
		continue
	profile_sub_paths.add(prof.sub_path)
	profiles.setdefault(prof.arch, []).append(prof)

# Use an empty profile for checking dependencies of
# packages that have empty KEYWORDS.
prof = ProfileDesc('**', 'stable', '', '')
profiles.setdefault(prof.arch, []).append(prof)

for x in repoman_settings.archlist():
	if x[0] == "~":
		continue
	if x not in profiles:
		print(red(
			"\"%s\" doesn't have a valid profile listed in profiles.desc." % x))
		print(red(
			"You need to either \"cvs update\" your profiles dir"
			" or follow this"))
		print(red(
			"up with the " + x + " team."))
		print()

liclist_deprecated = set()
if "DEPRECATED" in repoman_settings._license_manager._license_groups:
	liclist_deprecated.update(
		repoman_settings._license_manager.expandLicenseTokens(["@DEPRECATED"]))

if not liclist:
	logging.fatal("Couldn't find licenses?")
	sys.exit(1)

if not kwlist:
	logging.fatal("Couldn't read KEYWORDS from arch.list")
	sys.exit(1)

if not uselist:
	logging.fatal("Couldn't find use.desc?")
	sys.exit(1)

scanlist = []
if repolevel == 2:
	# we are inside a category directory
	catdir = reposplit[-1]
	if catdir not in categories:
		caterror(catdir)
	mydirlist = os.listdir(startdir)
	for x in mydirlist:
		if x == "CVS" or x.startswith("."):
			continue
		if os.path.isdir(startdir + "/" + x):
			scanlist.append(catdir + "/" + x)
	repo_subdir = catdir + os.sep
elif repolevel == 1:
	for x in categories:
		if not os.path.isdir(startdir + "/" + x):
			continue
		for y in os.listdir(startdir + "/" + x):
			if y == "CVS" or y.startswith("."):
				continue
			if os.path.isdir(startdir + "/" + x + "/" + y):
				scanlist.append(x + "/" + y)
	repo_subdir = ""
elif repolevel == 3:
	catdir = reposplit[-2]
	if catdir not in categories:
		caterror(catdir)
	scanlist.append(catdir + "/" + reposplit[-1])
	repo_subdir = scanlist[-1] + os.sep
else:
	msg = 'Repoman is unable to determine PORTDIR or PORTDIR_OVERLAY' + \
		' from the current working directory'
	logging.critical(msg)
	sys.exit(1)

repo_subdir_len = len(repo_subdir)
scanlist.sort()

logging.debug(
	"Found the following packages to scan:\n%s" % '\n'.join(scanlist))


dev_keywords = dev_keywords(profiles)

stats = {}
fails = {}

for x in qacats:
	stats[x] = 0
	fails[x] = []

xmllint_capable = False
metadata_dtd = os.path.join(repoman_settings["DISTDIR"], 'metadata.dtd')

if options.mode == "manifest":
	pass
elif not find_binary('xmllint'):
	print(red("!!! xmllint not found. Can't check metadata.xml.\n"))
	if options.xml_parse or repolevel == 3:
		print("%s sorry, xmllint is needed.  failing\n" % red("!!!"))
		sys.exit(1)
else:
	if not fetch_metadata_dtd():
		sys.exit(1)
	# this can be problematic if xmllint changes their output
	xmllint_capable = True

if options.mode == 'commit' and vcs:
	utilities.detect_vcs_conflicts(options, vcs)

if options.mode == "manifest":
	pass
elif options.pretend:
	print(green("\nRepoMan does a once-over of the neighborhood..."))
else:
	print(green("\nRepoMan scours the neighborhood..."))

new_ebuilds = set()
modified_ebuilds = set()
modified_changelogs = set()
mychanged = []
mynew = []
myremoved = []

if (options.if_modified != "y" and
	options.mode in ("manifest", "manifest-check")):
	pass
elif vcs == "cvs":
	mycvstree = cvstree.getentries("./", recursive=1)
	mychanged = cvstree.findchanged(mycvstree, recursive=1, basedir="./")
	mynew = cvstree.findnew(mycvstree, recursive=1, basedir="./")
	if options.if_modified == "y":
		myremoved = cvstree.findremoved(mycvstree, recursive=1, basedir="./")

elif vcs == "svn":
	with repoman_popen("svn status") as f:
		svnstatus = f.readlines()
	mychanged = [
		"./" + elem.split()[-1:][0]
		for elem in svnstatus
		if elem and elem[:1] in "MR"]
	mynew = [
		"./" + elem.split()[-1:][0]
		for elem in svnstatus
		if elem.startswith("A")]
	if options.if_modified == "y":
		myremoved = [
			"./" + elem.split()[-1:][0]
			for elem in svnstatus
			if elem.startswith("D")]

elif vcs == "git":
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
	if options.if_modified == "y":
		with repoman_popen(
			"git diff-index --name-only "
			"--relative --diff-filter=D HEAD") as f:
			myremoved = f.readlines()
		myremoved = ["./" + elem[:-1] for elem in myremoved]

elif vcs == "bzr":
	with repoman_popen("bzr status -S .") as f:
		bzrstatus = f.readlines()
	mychanged = [
		"./" + elem.split()[-1:][0].split('/')[-1:][0]
		for elem in bzrstatus
		if elem and elem[1:2] == "M"]
	mynew = [
		"./" + elem.split()[-1:][0].split('/')[-1:][0]
		for elem in bzrstatus
		if elem and (elem[1:2] == "NK" or elem[0:1] == "R")]
	if options.if_modified == "y":
		myremoved = [
			"./" + elem.split()[-3:-2][0].split('/')[-1:][0]
			for elem in bzrstatus
			if elem and (elem[1:2] == "K" or elem[0:1] == "R")]

elif vcs == "hg":
	with repoman_popen("hg status --no-status --modified .") as f:
		mychanged = f.readlines()
	mychanged = ["./" + elem.rstrip() for elem in mychanged]
	with repoman_popen("hg status --no-status --added .") as f:
		mynew = f.readlines()
	mynew = ["./" + elem.rstrip() for elem in mynew]
	if options.if_modified == "y":
		with repoman_popen("hg status --no-status --removed .") as f:
			myremoved = f.readlines()
		myremoved = ["./" + elem.rstrip() for elem in myremoved]

if vcs:
	new_ebuilds.update(x for x in mynew if x.endswith(".ebuild"))
	modified_ebuilds.update(x for x in mychanged if x.endswith(".ebuild"))
	modified_changelogs.update(
		x for x in chain(mychanged, mynew)
		if os.path.basename(x) == "ChangeLog")

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
	(vcs == "svn" and repolevel < 3 and options.mode != "commit")

# Build a regex from thirdpartymirrors for the SRC_URI.mirror check.
thirdpartymirrors = {}
for k, v in repoman_settings.thirdpartymirrors().items():
	for v in v:
		if not v.endswith("/"):
			v += "/"
		thirdpartymirrors[v] = k

try:
	herd_base = make_herd_base(
		os.path.join(repoman_settings["PORTDIR"], "metadata/herds.xml"))
except (EnvironmentError, ParseError, PermissionDenied) as e:
	err(str(e))
except FileNotFound:
	# TODO: Download as we do for metadata.dtd, but add a way to
	# disable for non-gentoo repoman users who may not have herds.
	herd_base = None

effective_scanlist = scanlist
if options.if_modified == "y":
	effective_scanlist = sorted(vcs_files_to_cps(
		chain(mychanged, mynew, myremoved)))

for x in effective_scanlist:
	# ebuilds and digests added to cvs respectively.
	logging.info("checking package %s" % x)
	# save memory by discarding xmatch caches from previous package(s)
	arch_xmatch_caches.clear()
	eadded = []
	catdir, pkgdir = x.split("/")
	checkdir = repodir + "/" + x
	checkdir_relative = ""
	if repolevel < 3:
		checkdir_relative = os.path.join(pkgdir, checkdir_relative)
	if repolevel < 2:
		checkdir_relative = os.path.join(catdir, checkdir_relative)
	checkdir_relative = os.path.join(".", checkdir_relative)
	generated_manifest = False

	do_manifest = options.mode == "manifest"
	do_digest_only = options.mode != 'manifest-check' and options.digest == 'y'
	do_commit_or_fix = options.mode in ('commit', 'fix')
	do_something = not options.pretend

	if do_manifest or do_digest_only or do_commit_or_fix and do_something:
		auto_assumed = set()
		fetchlist_dict = portage.FetchlistDict(
			checkdir, repoman_settings, portdb)
		if options.mode == 'manifest' and options.force:
			portage._doebuild_manifest_exempt_depend += 1
			try:
				distdir = repoman_settings['DISTDIR']
				mf = repoman_settings.repositories.get_repo_for_location(
					os.path.dirname(os.path.dirname(checkdir)))
				mf = mf.load_manifest(
					checkdir, distdir, fetchlist_dict=fetchlist_dict)
				mf.create(
					requiredDistfiles=None, assumeDistHashesAlways=True)
				for distfiles in fetchlist_dict.values():
					for distfile in distfiles:
						if os.path.isfile(os.path.join(distdir, distfile)):
							mf.fhashdict['DIST'].pop(distfile, None)
						else:
							auto_assumed.add(distfile)
				mf.write()
			finally:
				portage._doebuild_manifest_exempt_depend -= 1

		repoman_settings["O"] = checkdir
		try:
			generated_manifest = digestgen(
				mysettings=repoman_settings, myportdb=portdb)
		except portage.exception.PermissionDenied as e:
			generated_manifest = False
			writemsg_level(
				"!!! Permission denied: '%s'\n" % (e,),
				level=logging.ERROR, noiselevel=-1)

		if not generated_manifest:
			print("Unable to generate manifest.")
			dofail = 1

		if options.mode == "manifest":
			if not dofail and options.force and auto_assumed and \
				'assume-digests' in repoman_settings.features:
				# Show which digests were assumed despite the --force option
				# being given. This output will already have been shown by
				# digestgen() if assume-digests is not enabled, so only show
				# it here if assume-digests is enabled.
				pkgs = list(fetchlist_dict)
				pkgs.sort()
				portage.writemsg_stdout(
					"  digest.assumed %s" %
					portage.output.colorize(
						"WARN", str(len(auto_assumed)).rjust(18)) + "\n")
				for cpv in pkgs:
					fetchmap = fetchlist_dict[cpv]
					pf = portage.catsplit(cpv)[1]
					for distfile in sorted(fetchmap):
						if distfile in auto_assumed:
							portage.writemsg_stdout(
								"   %s::%s\n" % (pf, distfile))
			continue
		elif dofail:
			sys.exit(1)

	if not generated_manifest:
		repoman_settings['O'] = checkdir
		repoman_settings['PORTAGE_QUIET'] = '1'
		if not portage.digestcheck([], repoman_settings, strict=1):
			stats["manifest.bad"] += 1
			fails["manifest.bad"].append(os.path.join(x, 'Manifest'))
		repoman_settings.pop('PORTAGE_QUIET', None)

	if options.mode == 'manifest-check':
		continue

	checkdirlist = os.listdir(checkdir)
	ebuildlist = []
	pkgs = {}
	allvalid = True
	for y in checkdirlist:
		file_is_ebuild = y.endswith(".ebuild")
		file_should_be_non_executable = y in no_exec or file_is_ebuild

		if file_should_be_non_executable:
			file_is_executable = stat.S_IMODE(
				os.stat(os.path.join(checkdir, y)).st_mode) & 0o111

			if file_is_executable:
				stats["file.executable"] += 1
				fails["file.executable"].append(os.path.join(checkdir, y))
		if file_is_ebuild:
			pf = y[:-7]
			ebuildlist.append(pf)
			cpv = "%s/%s" % (catdir, pf)
			try:
				myaux = dict(zip(allvars, portdb.aux_get(cpv, allvars)))
			except KeyError:
				allvalid = False
				stats["ebuild.syntax"] += 1
				fails["ebuild.syntax"].append(os.path.join(x, y))
				continue
			except IOError:
				allvalid = False
				stats["ebuild.output"] += 1
				fails["ebuild.output"].append(os.path.join(x, y))
				continue
			if not portage.eapi_is_supported(myaux["EAPI"]):
				allvalid = False
				stats["EAPI.unsupported"] += 1
				fails["EAPI.unsupported"].append(os.path.join(x, y))
				continue
			pkgs[pf] = Package(
				cpv=cpv, metadata=myaux, root_config=root_config,
				type_name="ebuild")

	slot_keywords = {}

	if len(pkgs) != len(ebuildlist):
		# If we can't access all the metadata then it's totally unsafe to
		# commit since there's no way to generate a correct Manifest.
		# Do not try to do any more QA checks on this package since missing
		# metadata leads to false positives for several checks, and false
		# positives confuse users.
		can_force = False
		continue

	# Sort ebuilds in ascending order for the KEYWORDS.dropped check.
	ebuildlist = sorted(pkgs.values())
	ebuildlist = [pkg.pf for pkg in ebuildlist]

	for y in checkdirlist:
		index = repo_config.find_invalid_path_char(y)
		if index != -1:
			y_relative = os.path.join(checkdir_relative, y)
			if vcs is not None and not vcs_new_changed(y_relative):
				# If the file isn't in the VCS new or changed set, then
				# assume that it's an irrelevant temporary file (Manifest
				# entries are not generated for file names containing
				# prohibited characters). See bug #406877.
				index = -1
		if index != -1:
			stats["file.name"] += 1
			fails["file.name"].append(
				"%s/%s: char '%s'" % (checkdir, y, y[index]))

		if not (y in ("ChangeLog", "metadata.xml") or y.endswith(".ebuild")):
			continue
		f = None
		try:
			line = 1
			f = io.open(
				_unicode_encode(
					os.path.join(checkdir, y),
					encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'])
			for l in f:
				line += 1
		except UnicodeDecodeError as ue:
			stats["file.UTF8"] += 1
			s = ue.object[:ue.start]
			l2 = s.count("\n")
			line += l2
			if l2 != 0:
				s = s[s.rfind("\n") + 1:]
			fails["file.UTF8"].append(
				"%s/%s: line %i, just after: '%s'" % (checkdir, y, line, s))
		finally:
			if f is not None:
				f.close()

	if vcs in ("git", "hg") and check_ebuild_notadded:
		if vcs == "git":
			myf = repoman_popen(
				"git ls-files --others %s" %
				(portage._shell_quote(checkdir_relative),))
		if vcs == "hg":
			myf = repoman_popen(
				"hg status --no-status --unknown %s" %
				(portage._shell_quote(checkdir_relative),))
		for l in myf:
			if l[:-1][-7:] == ".ebuild":
				stats["ebuild.notadded"] += 1
				fails["ebuild.notadded"].append(
					os.path.join(x, os.path.basename(l[:-1])))
		myf.close()

	if vcs in ("cvs", "svn", "bzr") and check_ebuild_notadded:
		try:
			if vcs == "cvs":
				myf = open(checkdir + "/CVS/Entries", "r")
			if vcs == "svn":
				myf = repoman_popen(
					"svn status --depth=files --verbose " +
					portage._shell_quote(checkdir))
			if vcs == "bzr":
				myf = repoman_popen(
					"bzr ls -v --kind=file " +
					portage._shell_quote(checkdir))
			myl = myf.readlines()
			myf.close()
			for l in myl:
				if vcs == "cvs":
					if l[0] != "/":
						continue
					splitl = l[1:].split("/")
					if not len(splitl):
						continue
					if splitl[0][-7:] == ".ebuild":
						eadded.append(splitl[0][:-7])
				if vcs == "svn":
					if l[:1] == "?":
						continue
					if l[:7] == '      >':
						# tree conflict, new in subversion 1.6
						continue
					l = l.split()[-1]
					if l[-7:] == ".ebuild":
						eadded.append(os.path.basename(l[:-7]))
				if vcs == "bzr":
					if l[1:2] == "?":
						continue
					l = l.split()[-1]
					if l[-7:] == ".ebuild":
						eadded.append(os.path.basename(l[:-7]))
			if vcs == "svn":
				myf = repoman_popen(
					"svn status " +
					portage._shell_quote(checkdir))
				myl = myf.readlines()
				myf.close()
				for l in myl:
					if l[0] == "A":
						l = l.rstrip().split(' ')[-1]
						if l[-7:] == ".ebuild":
							eadded.append(os.path.basename(l[:-7]))
		except IOError:
			if vcs == "cvs":
				stats["CVS/Entries.IO_error"] += 1
				fails["CVS/Entries.IO_error"].append(checkdir + "/CVS/Entries")
			else:
				raise
			continue

	mf = repoman_settings.repositories.get_repo_for_location(
		os.path.dirname(os.path.dirname(checkdir)))
	mf = mf.load_manifest(checkdir, repoman_settings["DISTDIR"])
	mydigests = mf.getTypeDigests("DIST")

	fetchlist_dict = portage.FetchlistDict(checkdir, repoman_settings, portdb)
	myfiles_all = []
	src_uri_error = False
	for mykey in fetchlist_dict:
		try:
			myfiles_all.extend(fetchlist_dict[mykey])
		except portage.exception.InvalidDependString as e:
			src_uri_error = True
			try:
				portdb.aux_get(mykey, ["SRC_URI"])
			except KeyError:
				# This will be reported as an "ebuild.syntax" error.
				pass
			else:
				stats["SRC_URI.syntax"] += 1
				fails["SRC_URI.syntax"].append(
					"%s.ebuild SRC_URI: %s" % (mykey, e))
	del fetchlist_dict
	if not src_uri_error:
		# This test can produce false positives if SRC_URI could not
		# be parsed for one or more ebuilds. There's no point in
		# producing a false error here since the root cause will
		# produce a valid error elsewhere, such as "SRC_URI.syntax"
		# or "ebuild.sytax".
		myfiles_all = set(myfiles_all)
		for entry in mydigests:
			if entry not in myfiles_all:
				stats["digest.unused"] += 1
				fails["digest.unused"].append(checkdir + "::" + entry)
		for entry in myfiles_all:
			if entry not in mydigests:
				stats["digest.missing"] += 1
				fails["digest.missing"].append(checkdir + "::" + entry)
	del myfiles_all

	if os.path.exists(checkdir + "/files"):
		filesdirlist = os.listdir(checkdir + "/files")

		# Recurse through files directory, use filesdirlist as a stack;
		# appending directories as needed,
		# so people can't hide > 20k files in a subdirectory.
		while filesdirlist:
			y = filesdirlist.pop(0)
			relative_path = os.path.join(x, "files", y)
			full_path = os.path.join(repodir, relative_path)
			try:
				mystat = os.stat(full_path)
			except OSError as oe:
				if oe.errno == 2:
					# don't worry about it.  it likely was removed via fix above.
					continue
				else:
					raise oe
			if S_ISDIR(mystat.st_mode):
				# !!! VCS "portability" alert!  Need some function isVcsDir() or alike !!!
				if y == "CVS" or y == ".svn":
					continue
				for z in os.listdir(checkdir + "/files/" + y):
					if z == "CVS" or z == ".svn":
						continue
					filesdirlist.append(y + "/" + z)
			# Current policy is no files over 20 KiB, these are the checks.
			# File size between 20 KiB and 60 KiB causes a warning,
			# while file size over 60 KiB causes an error.
			elif mystat.st_size > 61440:
				stats["file.size.fatal"] += 1
				fails["file.size.fatal"].append(
					"(%d KiB) %s/files/%s" % (mystat.st_size // 1024, x, y))
			elif mystat.st_size > 20480:
				stats["file.size"] += 1
				fails["file.size"].append(
					"(%d KiB) %s/files/%s" % (mystat.st_size // 1024, x, y))

			index = repo_config.find_invalid_path_char(y)
			if index != -1:
				y_relative = os.path.join(checkdir_relative, "files", y)
				if vcs is not None and not vcs_new_changed(y_relative):
					# If the file isn't in the VCS new or changed set, then
					# assume that it's an irrelevant temporary file (Manifest
					# entries are not generated for file names containing
					# prohibited characters). See bug #406877.
					index = -1
			if index != -1:
				stats["file.name"] += 1
				fails["file.name"].append(
					"%s/files/%s: char '%s'" % (checkdir, y, y[index]))
	del mydigests

	if check_changelog and "ChangeLog" not in checkdirlist:
		stats["changelog.missing"] += 1
		fails["changelog.missing"].append(x + "/ChangeLog")

	musedict = {}
	# metadata.xml file check
	if "metadata.xml" not in checkdirlist:
		stats["metadata.missing"] += 1
		fails["metadata.missing"].append(x + "/metadata.xml")
	# metadata.xml parse check
	else:
		metadata_bad = False
		xml_info = {}
		xml_parser = _XMLParser(xml_info, target=_MetadataTreeBuilder())

		# read metadata.xml into memory
		try:
			_metadata_xml = xml.etree.ElementTree.parse(
				_unicode_encode(
					os.path.join(checkdir, "metadata.xml"),
					encoding=_encodings['fs'], errors='strict'),
				parser=xml_parser)
		except (ExpatError, SyntaxError, EnvironmentError) as e:
			metadata_bad = True
			stats["metadata.bad"] += 1
			fails["metadata.bad"].append("%s/metadata.xml: %s" % (x, e))
			del e
		else:
			if not hasattr(xml_parser, 'parser') or \
				sys.hexversion < 0x2070000 or \
				(sys.hexversion > 0x3000000 and sys.hexversion < 0x3020000):
				# doctype is not parsed with python 2.6 or 3.1
				pass
			else:
				if "XML_DECLARATION" not in xml_info:
					stats["metadata.bad"] += 1
					fails["metadata.bad"].append(
						"%s/metadata.xml: "
						"xml declaration is missing on first line, "
						"should be '%s'" % (x, metadata_xml_declaration))
				else:
					xml_version, xml_encoding, xml_standalone = \
						xml_info["XML_DECLARATION"]
					if xml_encoding is None or \
						xml_encoding.upper() != metadata_xml_encoding:
						stats["metadata.bad"] += 1
						if xml_encoding is None:
							encoding_problem = "but it is undefined"
						else:
							encoding_problem = "not '%s'" % xml_encoding
						fails["metadata.bad"].append(
							"%s/metadata.xml: "
							"xml declaration encoding should be '%s', %s" %
							(x, metadata_xml_encoding, encoding_problem))

				if "DOCTYPE" not in xml_info:
					metadata_bad = True
					stats["metadata.bad"] += 1
					fails["metadata.bad"].append(
						"%s/metadata.xml: %s" % (x, "DOCTYPE is missing"))
				else:
					doctype_name, doctype_system, doctype_pubid = \
						xml_info["DOCTYPE"]
					if doctype_system != metadata_dtd_uri:
						stats["metadata.bad"] += 1
						if doctype_system is None:
							system_problem = "but it is undefined"
						else:
							system_problem = "not '%s'" % doctype_system
						fails["metadata.bad"].append(
							"%s/metadata.xml: "
							"DOCTYPE: SYSTEM should refer to '%s', %s" %
							(x, metadata_dtd_uri, system_problem))

					if doctype_name != metadata_doctype_name:
						stats["metadata.bad"] += 1
						fails["metadata.bad"].append(
							"%s/metadata.xml: "
							"DOCTYPE: name should be '%s', not '%s'" %
							(x, metadata_doctype_name, doctype_name))

			# load USE flags from metadata.xml
			try:
				musedict = utilities.parse_metadata_use(_metadata_xml)
			except portage.exception.ParseError as e:
				metadata_bad = True
				stats["metadata.bad"] += 1
				fails["metadata.bad"].append("%s/metadata.xml: %s" % (x, e))
			else:
				for atom in chain(*musedict.values()):
					if atom is None:
						continue
					try:
						atom = Atom(atom)
					except InvalidAtom as e:
						stats["metadata.bad"] += 1
						fails["metadata.bad"].append(
							"%s/metadata.xml: Invalid atom: %s" % (x, e))
					else:
						if atom.cp != x:
							stats["metadata.bad"] += 1
							fails["metadata.bad"].append(
								"%s/metadata.xml: Atom contains "
								"unexpected cat/pn: %s" % (x, atom))

			# Run other metadata.xml checkers
			try:
				utilities.check_metadata(_metadata_xml, herd_base)
			except (utilities.UnknownHerdsError, ) as e:
				metadata_bad = True
				stats["metadata.bad"] += 1
				fails["metadata.bad"].append("%s/metadata.xml: %s" % (x, e))
				del e

		# Only carry out if in package directory or check forced
		if xmllint_capable and not metadata_bad:
			# xmlint can produce garbage output even on success, so only dump
			# the ouput when it fails.
			st, out = repoman_getstatusoutput(
				"xmllint --nonet --noout --dtdvalid %s %s" % (
					portage._shell_quote(metadata_dtd),
					portage._shell_quote(
						os.path.join(checkdir, "metadata.xml"))))
			if st != os.EX_OK:
				print(red("!!!") + " metadata.xml is invalid:")
				for z in out.splitlines():
					print(red("!!! ") + z)
				stats["metadata.bad"] += 1
				fails["metadata.bad"].append(x + "/metadata.xml")

		del metadata_bad
	muselist = frozenset(musedict)

	changelog_path = os.path.join(checkdir_relative, "ChangeLog")
	changelog_modified = changelog_path in modified_changelogs

	# detect unused local USE-descriptions
	used_useflags = set()

	for y in ebuildlist:
		relative_path = os.path.join(x, y + ".ebuild")
		full_path = os.path.join(repodir, relative_path)
		ebuild_path = y + ".ebuild"
		if repolevel < 3:
			ebuild_path = os.path.join(pkgdir, ebuild_path)
		if repolevel < 2:
			ebuild_path = os.path.join(catdir, ebuild_path)
		ebuild_path = os.path.join(".", ebuild_path)
		if check_changelog and not changelog_modified \
			and ebuild_path in new_ebuilds:
			stats['changelog.ebuildadded'] += 1
			fails['changelog.ebuildadded'].append(relative_path)

		vcs_is_cvs_or_svn_or_bzr = vcs in ("cvs", "svn", "bzr")
		check_ebuild_really_notadded = check_ebuild_notadded and y not in eadded
		if vcs_is_cvs_or_svn_or_bzr and check_ebuild_really_notadded:
			# ebuild not added to vcs
			stats["ebuild.notadded"] += 1
			fails["ebuild.notadded"].append(x + "/" + y + ".ebuild")
		myesplit = portage.pkgsplit(y)

		is_bad_split = myesplit is None or myesplit[0] != x.split("/")[-1]

		if is_bad_split:
			is_pv_toolong = pv_toolong_re.search(myesplit[1])
			is_pv_toolong2 = pv_toolong_re.search(myesplit[2])

			if is_pv_toolong or is_pv_toolong2:
				stats["ebuild.invalidname"] += 1
				fails["ebuild.invalidname"].append(x + "/" + y + ".ebuild")
				continue
		elif myesplit[0] != pkgdir:
			print(pkgdir, myesplit[0])
			stats["ebuild.namenomatch"] += 1
			fails["ebuild.namenomatch"].append(x + "/" + y + ".ebuild")
			continue

		pkg = pkgs[y]

		if pkg.invalid:
			allvalid = False
			for k, msgs in pkg.invalid.items():
				for msg in msgs:
					stats[k] += 1
					fails[k].append("%s: %s" % (relative_path, msg))
			continue

		myaux = pkg._metadata
		eapi = myaux["EAPI"]
		inherited = pkg.inherited
		live_ebuild = live_eclasses.intersection(inherited)

		if repo_config.eapi_is_banned(eapi):
			stats["repo.eapi.banned"] += 1
			fails["repo.eapi.banned"].append(
				"%s: %s" % (relative_path, eapi))

		elif repo_config.eapi_is_deprecated(eapi):
			stats["repo.eapi.deprecated"] += 1
			fails["repo.eapi.deprecated"].append(
				"%s: %s" % (relative_path, eapi))

		for k, v in myaux.items():
			if not isinstance(v, basestring):
				continue
			m = non_ascii_re.search(v)
			if m is not None:
				stats["variable.invalidchar"] += 1
				fails["variable.invalidchar"].append(
					"%s: %s variable contains non-ASCII "
					"character at position %s" %
					(relative_path, k, m.start() + 1))

		if not src_uri_error:
			# Check that URIs don't reference a server from thirdpartymirrors.
			for uri in portage.dep.use_reduce(
				myaux["SRC_URI"], matchall=True, is_src_uri=True, eapi=eapi, flat=True):
				contains_mirror = False
				for mirror, mirror_alias in thirdpartymirrors.items():
					if uri.startswith(mirror):
						contains_mirror = True
						break
				if not contains_mirror:
					continue

				new_uri = "mirror://%s/%s" % (mirror_alias, uri[len(mirror):])
				stats["SRC_URI.mirror"] += 1
				fails["SRC_URI.mirror"].append(
					"%s: '%s' found in thirdpartymirrors, use '%s'" %
					(relative_path, mirror, new_uri))

		if myaux.get("PROVIDE"):
			stats["virtual.oldstyle"] += 1
			fails["virtual.oldstyle"].append(relative_path)

		for pos, missing_var in enumerate(missingvars):
			if not myaux.get(missing_var):
				if catdir == "virtual" and \
					missing_var in ("HOMEPAGE", "LICENSE"):
					continue
				if live_ebuild and missing_var == "KEYWORDS":
					continue
				myqakey = missingvars[pos] + ".missing"
				stats[myqakey] += 1
				fails[myqakey].append(x + "/" + y + ".ebuild")

		if catdir == "virtual":
			for var in ("HOMEPAGE", "LICENSE"):
				if myaux.get(var):
					myqakey = var + ".virtual"
					stats[myqakey] += 1
					fails[myqakey].append(relative_path)

		# 14 is the length of DESCRIPTION=""
		if len(myaux['DESCRIPTION']) > max_desc_len:
			stats['DESCRIPTION.toolong'] += 1
			fails['DESCRIPTION.toolong'].append(
				"%s: DESCRIPTION is %d characters (max %d)" %
				(relative_path, len(myaux['DESCRIPTION']), max_desc_len))

		keywords = myaux["KEYWORDS"].split()
		if not options.straight_to_stable:
			stable_keywords = []
			for keyword in keywords:
				if not keyword.startswith("~") and \
					not keyword.startswith("-"):
					stable_keywords.append(keyword)
			if stable_keywords:
				if ebuild_path in new_ebuilds and catdir != "virtual":
					stable_keywords.sort()
					stats["KEYWORDS.stable"] += 1
					fails["KEYWORDS.stable"].append(
						relative_path + " added with stable keywords: %s" % \
							" ".join(stable_keywords))

		ebuild_archs = set(
			kw.lstrip("~") for kw in keywords if not kw.startswith("-"))

		previous_keywords = slot_keywords.get(pkg.slot)
		if previous_keywords is None:
			slot_keywords[pkg.slot] = set()
		elif ebuild_archs and "*" not in ebuild_archs and not live_ebuild:
			dropped_keywords = previous_keywords.difference(ebuild_archs)
			if dropped_keywords:
				stats["KEYWORDS.dropped"] += 1
				fails["KEYWORDS.dropped"].append(
					"%s: %s" %
					(relative_path, " ".join(sorted(dropped_keywords))))

		slot_keywords[pkg.slot].update(ebuild_archs)

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
				stats["KEYWORDS.stupid"] += 1
				fails["KEYWORDS.stupid"].append(x + "/" + y + ".ebuild")

		"""
		Ebuilds that inherit a "Live" eclass (darcs,subversion,git,cvs,etc..) should
		not be allowed to be marked stable
		"""
		if live_ebuild and repo_config.name == "gentoo":
			bad_stable_keywords = []
			for keyword in keywords:
				if not keyword.startswith("~") and \
					not keyword.startswith("-"):
					bad_stable_keywords.append(keyword)
				del keyword
			if bad_stable_keywords:
				stats["LIVEVCS.stable"] += 1
				fails["LIVEVCS.stable"].append(
					"%s/%s.ebuild with stable keywords:%s " %
					(x, y, bad_stable_keywords))
			del bad_stable_keywords

			if keywords and not has_global_mask(pkg):
				stats["LIVEVCS.unmasked"] += 1
				fails["LIVEVCS.unmasked"].append(relative_path)

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
		catpkg = catdir + "/" + y

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
					stats[mytype + '.suspect'] += 1
					fails[mytype + '.suspect'].append(
						"%s: 'test?' USE conditional in %s" %
						(relative_path, mytype))

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
							stats['virtual.suspect'] += 1
							fails['virtual.suspect'].append(
								relative_path +
								": %s: consider using '%s' instead of '%s'" %
								(mytype, suspect_virtual[atom.cp], atom))
						if not is_blocker and \
							atom.cp.startswith("perl-core/"):
							stats['dependency.perlcore'] += 1
							fails['dependency.perlcore'].append(
								relative_path +
								": %s: please use '%s' instead of '%s'" %
								(mytype, atom.replace("perl-core/","virtual/perl-"), atom))

					if buildtime and \
						not is_blocker and \
						not inherited_java_eclass and \
						atom.cp == "virtual/jdk":
						stats['java.eclassesnotused'] += 1
						fails['java.eclassesnotused'].append(relative_path)
					elif buildtime and \
						not is_blocker and \
						not inherited_wxwidgets_eclass and \
						atom.cp == "x11-libs/wxGTK":
						stats['wxwidgets.eclassnotused'] += 1
						fails['wxwidgets.eclassnotused'].append(
							"%s: %ss on x11-libs/wxGTK without inheriting"
							" wxwidgets.eclass" % (relative_path, mytype))
					elif runtime:
						if not is_blocker and \
							atom.cp in suspect_rdepend:
							stats[mytype + '.suspect'] += 1
							fails[mytype + '.suspect'].append(
								relative_path + ": '%s'" % atom)

					if atom.operator == "~" and \
						portage.versions.catpkgsplit(atom.cpv)[3] != "r0":
						qacat = 'dependency.badtilde'
						stats[qacat] += 1
						fails[qacat].append(
							"%s: %s uses the ~ operator"
							" with a non-zero revision: '%s'" %
							(relative_path, mytype, atom))

					check_missingslot(atom, mytype, eapi, portdb, stats, fails,
						relative_path, myaux)

			type_list.extend([mytype] * (len(badsyntax) - len(type_list)))

		for m, b in zip(type_list, badsyntax):
			if m.endswith("DEPEND"):
				qacat = "dependency.syntax"
			else:
				qacat = m + ".syntax"
			stats[qacat] += 1
			fails[qacat].append("%s: %s: %s" % (relative_path, m, b))

		badlicsyntax = len([z for z in type_list if z == "LICENSE"])
		badprovsyntax = len([z for z in type_list if z == "PROVIDE"])
		baddepsyntax = len(type_list) != badlicsyntax + badprovsyntax
		badlicsyntax = badlicsyntax > 0
		badprovsyntax = badprovsyntax > 0

		# uselist checks - global
		myuse = []
		default_use = []
		for myflag in myaux["IUSE"].split():
			flag_name = myflag.lstrip("+-")
			used_useflags.add(flag_name)
			if myflag != flag_name:
				default_use.append(myflag)
			if flag_name not in uselist:
				myuse.append(flag_name)

		# uselist checks - metadata
		for mypos in range(len(myuse) - 1, -1, -1):
			if myuse[mypos] and (myuse[mypos] in muselist):
				del myuse[mypos]

		if default_use and not eapi_has_iuse_defaults(eapi):
			for myflag in default_use:
				stats['EAPI.incompatible'] += 1
				fails['EAPI.incompatible'].append(
					"%s: IUSE defaults"
					" not supported with EAPI='%s': '%s'" %
					(relative_path, eapi, myflag))

		for mypos in range(len(myuse)):
			stats["IUSE.invalid"] += 1
			fails["IUSE.invalid"].append(x + "/" + y + ".ebuild: %s" % myuse[mypos])

		# Check for outdated RUBY targets
		old_ruby_eclasses = ["ruby-ng", "ruby-fakegem", "ruby"]
		is_old_ruby_eclass_inherited = filter(
			lambda e: e in inherited, old_ruby_eclasses)
		if is_old_ruby_eclass_inherited:
			ruby_intersection = pkg.iuse.all.intersection(ruby_deprecated)
			if ruby_intersection:
				for myruby in ruby_intersection:
					stats["IUSE.rubydeprecated"] += 1
					fails["IUSE.rubydeprecated"].append(
						(relative_path + ": Deprecated ruby target: %s") % myruby)

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
					stats["LICENSE.invalid"] += 1
					fails["LICENSE.invalid"].append(x + "/" + y + ".ebuild: %s" % lic)
				elif lic in liclist_deprecated:
					stats["LICENSE.deprecated"] += 1
					fails["LICENSE.deprecated"].append("%s: %s" % (relative_path, lic))

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
					stats["KEYWORDS.invalid"] += 1
					fails["KEYWORDS.invalid"].append(
						"%s/%s.ebuild: %s" % (x, y, mykey))
				elif myskey not in profiles:
					stats["KEYWORDS.invalid"] += 1
					fails["KEYWORDS.invalid"].append(
						"%s/%s.ebuild: %s (profile invalid)" % (x, y, mykey))

		# restrict checks
		myrestrict = None
		try:
			myrestrict = portage.dep.use_reduce(
				myaux["RESTRICT"], matchall=1, flat=True)
		except portage.exception.InvalidDependString as e:
			stats["RESTRICT.syntax"] += 1
			fails["RESTRICT.syntax"].append(
				"%s: RESTRICT: %s" % (relative_path, e))
			del e
		if myrestrict:
			myrestrict = set(myrestrict)
			mybadrestrict = myrestrict.difference(valid_restrict)
			if mybadrestrict:
				stats["RESTRICT.invalid"] += len(mybadrestrict)
				for mybad in mybadrestrict:
					fails["RESTRICT.invalid"].append(x + "/" + y + ".ebuild: %s" % mybad)
		# REQUIRED_USE check
		required_use = myaux["REQUIRED_USE"]
		if required_use:
			if not eapi_has_required_use(eapi):
				stats['EAPI.incompatible'] += 1
				fails['EAPI.incompatible'].append(
					"%s: REQUIRED_USE"
					" not supported with EAPI='%s'" % (relative_path, eapi,))
			try:
				portage.dep.check_required_use(
					required_use, (), pkg.iuse.is_valid_flag, eapi=eapi)
			except portage.exception.InvalidDependString as e:
				stats["REQUIRED_USE.syntax"] += 1
				fails["REQUIRED_USE.syntax"].append(
					"%s: REQUIRED_USE: %s" % (relative_path, e))
				del e

		# Syntax Checks
		relative_path = os.path.join(x, y + ".ebuild")
		full_path = os.path.join(repodir, relative_path)
		if not vcs_preserves_mtime:
			if ebuild_path not in new_ebuilds and \
				ebuild_path not in modified_ebuilds:
				pkg.mtime = None
		try:
			# All ebuilds should have utf_8 encoding.
			f = io.open(
				_unicode_encode(
					full_path, encoding=_encodings['fs'], errors='strict'),
				mode='r', encoding=_encodings['repo.content'])
			try:
				for check_name, e in run_checks(f, pkg):
					stats[check_name] += 1
					fails[check_name].append(relative_path + ': %s' % e)
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

			trees[root]["porttree"].settings = dep_settings
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
					Atom("%s::%s" % (pkg.cp, repo_config.name)))
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
						use="all", mode=matchmode, trees=trees)

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
							stats[mykey] += 1
							fails[mykey].append("%s: %s: %s(%s)\n%s"
								% (relative_path, mytype, keyword,
								prof, pformat(atoms, indent=6)))
					else:
						stats[mykey] += 1
						fails[mykey].append("%s: %s: %s(%s)\n%s"
							% (relative_path, mytype, keyword,
							prof, pformat(atoms, indent=6)))

		if not baddepsyntax and unknown_pkgs:
			type_map = {}
			for mytype, atom in unknown_pkgs:
				type_map.setdefault(mytype, set()).add(atom)
			for mytype, atoms in type_map.items():
				stats["dependency.unknown"] += 1
				fails["dependency.unknown"].append(
					"%s: %s: %s" % (
						relative_path, mytype, ", ".join(sorted(atoms))))

	# check if there are unused local USE-descriptions in metadata.xml
	# (unless there are any invalids, to avoid noise)
	if allvalid:
		for myflag in muselist.difference(used_useflags):
			stats["metadata.warning"] += 1
			fails["metadata.warning"].append(
				"%s/metadata.xml: unused local USE-description: '%s'" %
				(x, myflag))

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
	if not stats[x]:
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
	'column': utilities.format_qa_output_column,
	'default': utilities.format_qa_output
}

format_output = format_outputs.get(
	options.output_style, format_outputs['default'])
format_output(f, stats, fails, dofull, dofail, options, qawarnings)

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
		print(
			green("RepoMan sez:"),
			"\"You're only giving me a partial QA payment?\n"
			"              I'll take it this time, but I'm not happy.\"")
	elif not dofail:
		print(
			green("RepoMan sez:"),
			"\"If everyone were like you, I'd be out of business!\"")
	elif dofail:
		print(bad("Please fix these important QA issues first."))
		print(
			green("RepoMan sez:"),
			"\"Make your QA payment on time"
			" and you'll never see the likes of me.\"\n")
		sys.exit(1)
else:
	if dofail and can_force and options.force and not options.pretend:
		print(
			green("RepoMan sez:"),
			" \"You want to commit even with these QA issues?\n"
			"              I'll take it this time, but I'm not happy.\"\n")
	elif dofail:
		if options.force and not can_force:
			print(bad(
				"The --force option has been disabled"
				" due to extraordinary issues."))
		print(bad("Please fix these important QA issues first."))
		print(
			green("RepoMan sez:"),
			"\"Make your QA payment on time"
			" and you'll never see the likes of me.\"\n")
		sys.exit(1)

	if options.pretend:
		print(
			green("RepoMan sez:"),
			"\"So, you want to play it safe. Good call.\"\n")

	myunadded = []
	if vcs == "cvs":
		try:
			myvcstree = portage.cvstree.getentries("./", recursive=1)
			myunadded = portage.cvstree.findunadded(
				myvcstree, recursive=1, basedir="./")
		except SystemExit as e:
			raise  # TODO propagate this
		except:
			err("Error retrieving CVS tree; exiting.")
	if vcs == "svn":
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
	if vcs == "git":
		# get list of files not under version control or missing
		myf = repoman_popen("git ls-files --others")
		myunadded = ["./" + elem[:-1] for elem in myf]
		myf.close()
	if vcs == "bzr":
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
	if vcs == "hg":
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
			if repo_config.find_invalid_path_char(myunadded[x]) != -1:
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

	if vcs == "hg" and mydeleted:
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

	if vcs == "cvs":
		mycvstree = cvstree.getentries("./", recursive=1)
		mychanged = cvstree.findchanged(mycvstree, recursive=1, basedir="./")
		mynew = cvstree.findnew(mycvstree, recursive=1, basedir="./")
		myremoved = portage.cvstree.findremoved(mycvstree, recursive=1, basedir="./")
		bin_blob_pattern = re.compile("^-kb$")
		no_expansion = set(portage.cvstree.findoption(
			mycvstree, bin_blob_pattern, recursive=1, basedir="./"))

	if vcs == "svn":
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

	elif vcs == "git":
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

	if vcs == "bzr":
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

	if vcs == "hg":
		with repoman_popen("hg status --no-status --modified .") as f:
			mychanged = f.readlines()
		mychanged = ["./" + elem.rstrip() for elem in mychanged]

		with repoman_popen("hg status --no-status --added .") as f:
			mynew = f.readlines()
		mynew = ["./" + elem.rstrip() for elem in mynew]

		with repoman_popen("hg status --no-status --removed .") as f:
			myremoved = f.readlines()
		myremoved = ["./" + elem.rstrip() for elem in myremoved]

	if vcs:
		if not (mychanged or mynew or myremoved or (vcs == "hg" and mydeleted)):
			print(green("RepoMan sez:"), "\"Doing nothing is not always good for QA.\"")
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
			exithandler()
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

	if vcs == "git":
		# Use new footer only for git (see bug #438364).
		commit_footer = "\n\nPackage-Manager: portage-%s" % portage_version
		if report_options:
			commit_footer += "\nRepoMan-Options: " + " ".join(report_options)
		if sign_manifests:
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
			(portage_version, vcs, unameout)
		if report_options:
			commit_footer += ", RepoMan options: " + " ".join(report_options)
		if sign_manifests:
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
			chain(myupdates, mymanifests, myremoved))):
			catdir, pkgdir = x.split("/")
			checkdir = repodir + "/" + x
			checkdir_relative = ""
			if repolevel < 3:
				checkdir_relative = os.path.join(pkgdir, checkdir_relative)
			if repolevel < 2:
				checkdir_relative = os.path.join(catdir, checkdir_relative)
			checkdir_relative = os.path.join(".", checkdir_relative)

			changelog_path = os.path.join(checkdir_relative, "ChangeLog")
			changelog_modified = changelog_path in modified_changelogs
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
				os.path.join(repodir, 'skel.ChangeLog'),
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
		add_cmd = [vcs, "add"]
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
					"Exiting on %s error code: %s\n" % (vcs, retcode))
				sys.exit(retcode)

		myupdates += myautoadd

	print("* %s files being committed..." % green(str(len(myupdates))), end=' ')

	if vcs not in ('cvs', 'svn'):
		# With git, bzr and hg, there's never any keyword expansion, so
		# there's no need to regenerate manifests and all files will be
		# committed in one big commit at the end.
		print()
	elif not repo_config.thin_manifest:
		if vcs == 'cvs':
			headerstring = "'\$(Header|Id).*\$'"
		elif vcs == "svn":
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
			if vcs == "cvs":
				if myfile in no_expansion:
					continue

			# for SVN, expansion contains files that are included in expansion
			elif vcs == "svn":
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
			"* Files with headers will "
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

		commit_cmd = [vcs]
		commit_cmd.extend(vcs_global_opts)
		commit_cmd.append("commit")
		commit_cmd.extend(vcs_local_opts)
		commit_cmd.extend(["-F", commitmessagefile])
		commit_cmd.extend(myfiles)

		try:
			if options.pretend:
				print("(%s)" % (" ".join(commit_cmd),))
			else:
				retval = spawn(commit_cmd, env=commit_env)
				if retval != os.EX_OK:
					writemsg_level(
						"!!! Exiting on %s (shell) "
						"error code: %s\n" % (vcs, retval),
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
		print(
			green("RepoMan sez:"),
			"\"You're rather crazy... "
			"doing the entire repository.\"\n")

	if vcs in ('cvs', 'svn') and (myupdates or myremoved):

		for x in sorted(vcs_files_to_cps(
			chain(myupdates, myremoved, mymanifests))):
			repoman_settings["O"] = os.path.join(repodir, x)
			digestgen(mysettings=repoman_settings, myportdb=portdb)

	elif broken_changelog_manifests:
		for x in broken_changelog_manifests:
			repoman_settings["O"] = os.path.join(repodir, x)
			digestgen(mysettings=repoman_settings, myportdb=portdb)

	signed = False
	if sign_manifests:
		signed = True
		try:
			for x in sorted(vcs_files_to_cps(
				chain(myupdates, myremoved, mymanifests))):
				repoman_settings["O"] = os.path.join(repodir, x)
				manifest_path = os.path.join(repoman_settings["O"], "Manifest")
				if not need_signature(manifest_path):
					continue
				gpgsign(manifest_path)
		except portage.exception.PortageException as e:
			portage.writemsg("!!! %s\n" % str(e))
			portage.writemsg("!!! Disabled FEATURES='sign'\n")
			signed = False

	if vcs == 'git':
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
					"error code: %s\n" % (vcs, retval),
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
		if options.pretend and vcs is None:
			# substitute a bogus value for pretend output
			commit_cmd.append("cvs")
		else:
			commit_cmd.append(vcs)
		commit_cmd.extend(vcs_global_opts)
		commit_cmd.append("commit")
		commit_cmd.extend(vcs_local_opts)
		if vcs == "hg":
			commit_cmd.extend(["--logfile", commitmessagefile])
			commit_cmd.extend(myfiles)
		else:
			commit_cmd.extend(["-F", commitmessagefile])
			commit_cmd.extend(f.lstrip("./") for f in myfiles)

		try:
			if options.pretend:
				print("(%s)" % (" ".join(commit_cmd),))
			else:
				retval = spawn(commit_cmd, env=commit_env)
				if retval != os.EX_OK:
					if repo_config.sign_commit and vcs == 'git' and \
						not git_supports_gpg_sign():
						# Inform user that newer git is needed (bug #403323).
						logging.error(
							"Git >=1.7.9 is required for signed commits!")

					writemsg_level(
						"!!! Exiting on %s (shell) "
						"error code: %s\n" % (vcs, retval),
						level=logging.ERROR, noiselevel=-1)
					sys.exit(retval)
		finally:
			try:
				os.unlink(commitmessagefile)
			except OSError:
				pass

	print()
	if vcs:
		print("Commit complete.")
	else:
		print(
			"repoman was too scared"
			" by not seeing any familiar version control file"
			" that he forgot to commit anything")
	print(
		green("RepoMan sez:"),
		"\"If everyone were like you, I'd be out of business!\"\n")
sys.exit(0)
