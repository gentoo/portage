# Copyright 2010-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import bz2
import fnmatch
import tempfile
import portage

from itertools import permutations
from portage import os
from portage import shutil
from portage.const import (
	GLOBAL_CONFIG_PATH,
	PORTAGE_BIN_PATH,
	USER_CONFIG_PATH,
)
from portage.process import find_binary
from portage.dep import Atom, _repo_separator
from portage.package.ebuild.config import config
from portage.package.ebuild.digestgen import digestgen
from portage._sets import load_default_config
from portage._sets.base import InternalPackageSet
from portage.tests import cnf_path
from portage.util import ensure_dirs, normalize_path
from portage.versions import catsplit

import _emerge
from _emerge.actions import _calc_depclean
from _emerge.Blocker import Blocker
from _emerge.create_depgraph_params import create_depgraph_params
from _emerge.DependencyArg import DependencyArg
from _emerge.depgraph import backtrack_depgraph
from _emerge.RootConfig import RootConfig

try:
	from repoman.tests import cnf_path_repoman
except ImportError:
	cnf_path_repoman = None


class ResolverPlayground:
	"""
	This class helps to create the necessary files on disk and
	the needed settings instances, etc. for the resolver to do
	its work.
	"""

	config_files = frozenset(("eapi", "layout.conf", "make.conf", "modules", "package.accept_keywords",
		"package.keywords", "package.license", "package.mask", "package.properties",
		"package.provided", "packages",
		"package.unmask",
		"package.use",
		"package.use.aliases",
		"package.use.force",
		"package.use.mask",
		"package.use.stable.force",
		"package.use.stable.mask",
		"soname.provided",
		"unpack_dependencies", "use.aliases", "use.force", "use.mask", "layout.conf"))

	metadata_xml_template = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "https://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
<maintainer type="person">
<email>maintainer-needed@gentoo.org</email>
<description>Description of the maintainership</description>
</maintainer>
<longdescription>Long description of the package</longdescription>
<use>
%(flags)s
</use>
</pkgmetadata>
"""

	portage_bin = (
		'ebuild',
		'egencache',
		'emerge',
		'emerge-webrsync',
		'emirrordist',
		'glsa-check',
		'portageq',
		'quickpkg',
	)

	portage_sbin = (
		'archive-conf',
		'dispatch-conf',
		'emaint',
		'env-update',
		'etc-update',
		'fixpackages',
		'regenworld',
	)

	def __init__(self, ebuilds={}, binpkgs={}, installed={}, profile={}, repo_configs={}, \
		user_config={}, sets={}, world=[], world_sets=[], distfiles={}, eclasses={},
		eprefix=None, targetroot=False, debug=False):
		"""
		ebuilds: cpv -> metadata mapping simulating available ebuilds.
		installed: cpv -> metadata mapping simulating installed packages.
			If a metadata key is missing, it gets a default value.
		profile: settings defined by the profile.
		"""

		self.debug = debug
		if eprefix is None:
			self.eprefix = normalize_path(tempfile.mkdtemp())

			# EPREFIX/bin is used by fake true_binaries. Real binaries goes into EPREFIX/usr/bin
			eubin = os.path.join(self.eprefix, "usr", "bin")
			ensure_dirs(eubin)
			for x in self.portage_bin:
				os.symlink(os.path.join(PORTAGE_BIN_PATH, x), os.path.join(eubin, x))

			eusbin = os.path.join(self.eprefix, "usr", "sbin")
			ensure_dirs(eusbin)
			for x in self.portage_sbin:
				os.symlink(os.path.join(PORTAGE_BIN_PATH, x), os.path.join(eusbin, x))

			essential_binaries = (
				"awk",
				"basename",
				"bzip2",
				"cat",
				"chgrp",
				"chmod",
				"chown",
				"comm",
				"cp",
				"egrep",
				"env",
				"find",
				"grep",
				"head",
				"install",
				"ln",
				"mkdir",
				"mkfifo",
				"mktemp",
				"mv",
				"readlink",
				"rm",
				"sed",
				"sort",
				"tar",
				"tr",
				"uname",
				"uniq",
				"xargs",
				"zstd",
			)
			# Exclude internal wrappers from PATH lookup.
			orig_path = os.environ['PATH']
			included_paths = []
			for path in orig_path.split(':'):
				if path and not fnmatch.fnmatch(path, '*/portage/*/ebuild-helpers*'):
					included_paths.append(path)
			try:
				os.environ['PATH'] = ':'.join(included_paths)
				for x in essential_binaries:
					path = find_binary(x)
					if path is None:
						raise portage.exception.CommandNotFound(x)
					os.symlink(path, os.path.join(eubin, x))
			finally:
				os.environ['PATH'] = orig_path
		else:
			self.eprefix = normalize_path(eprefix)

		# Tests may override portage.const.EPREFIX in order to
		# simulate a prefix installation. It's reasonable to do
		# this because tests should be self-contained such that
		# the "real" value of portage.const.EPREFIX is entirely
		# irrelevant (see bug #492932).
		self._orig_eprefix = portage.const.EPREFIX
		portage.const.EPREFIX = self.eprefix.rstrip(os.sep)

		self.eroot = self.eprefix + os.sep
		if targetroot:
			self.target_root = os.path.join(self.eroot, 'target_root')
		else:
			self.target_root = os.sep
		self.distdir = os.path.join(self.eroot, "var", "portage", "distfiles")
		self.pkgdir = os.path.join(self.eprefix, "pkgdir")
		self.vdbdir = os.path.join(self.eroot, "var/db/pkg")
		os.makedirs(self.vdbdir)

		if not debug:
			portage.util.noiselimit = -2

		self._repositories = {}
		#Make sure the main repo is always created
		self._get_repo_dir("test_repo")

		self._create_distfiles(distfiles)
		self._create_ebuilds(ebuilds)
		self._create_binpkgs(binpkgs)
		self._create_installed(installed)
		self._create_profile(ebuilds, eclasses, installed, profile, repo_configs, user_config, sets)
		self._create_world(world, world_sets)

		self.settings, self.trees = self._load_config()

		self._create_ebuild_manifests(ebuilds)

		portage.util.noiselimit = 0

	def reload_config(self):
		"""
		Reload configuration from disk, which is useful if it has
		been modified after the constructor has been called.
		"""
		for eroot in self.trees:
			portdb = self.trees[eroot]["porttree"].dbapi
			portdb.close_caches()
		self.settings, self.trees = self._load_config()

	def _get_repo_dir(self, repo):
		"""
		Create the repo directory if needed.
		"""
		if repo not in self._repositories:
			if repo == "test_repo":
				self._repositories["DEFAULT"] = {"main-repo": repo}

			repo_path = os.path.join(self.eroot, "var", "repositories", repo)
			self._repositories[repo] = {"location": repo_path}
			profile_path = os.path.join(repo_path, "profiles")

			try:
				os.makedirs(profile_path)
			except os.error:
				pass

			repo_name_file = os.path.join(profile_path, "repo_name")
			with open(repo_name_file, "w") as f:
				f.write("%s\n" % repo)

		return self._repositories[repo]["location"]

	def _create_distfiles(self, distfiles):
		os.makedirs(self.distdir)
		for k, v in distfiles.items():
			with open(os.path.join(self.distdir, k), 'wb') as f:
				f.write(v)

	def _create_ebuilds(self, ebuilds):
		for cpv in ebuilds:
			a = Atom("=" + cpv, allow_repo=True)
			repo = a.repo
			if repo is None:
				repo = "test_repo"

			metadata = ebuilds[cpv].copy()
			copyright_header = metadata.pop("COPYRIGHT_HEADER", None)
			eapi = metadata.pop("EAPI", "0")
			misc_content = metadata.pop("MISC_CONTENT", None)
			metadata.setdefault("DEPEND", "")
			metadata.setdefault("SLOT", "0")
			metadata.setdefault("KEYWORDS", "x86")
			metadata.setdefault("IUSE", "")

			unknown_keys = set(metadata).difference(
				portage.dbapi.dbapi._known_keys)
			if unknown_keys:
				raise ValueError("metadata of ebuild '%s' contains unknown keys: %s" %
					(cpv, sorted(unknown_keys)))

			repo_dir = self._get_repo_dir(repo)
			ebuild_dir = os.path.join(repo_dir, a.cp)
			ebuild_path = os.path.join(ebuild_dir, a.cpv.split("/")[1] + ".ebuild")
			try:
				os.makedirs(ebuild_dir)
			except os.error:
				pass

			with open(ebuild_path, "w") as f:
				if copyright_header is not None:
					f.write(copyright_header)
				f.write('EAPI="%s"\n' % eapi)
				for k, v in metadata.items():
					f.write('%s="%s"\n' % (k, v))
				if misc_content is not None:
					f.write(misc_content)

	def _create_ebuild_manifests(self, ebuilds):
		tmpsettings = config(clone=self.settings)
		tmpsettings['PORTAGE_QUIET'] = '1'
		for cpv in ebuilds:
			a = Atom("=" + cpv, allow_repo=True)
			repo = a.repo
			if repo is None:
				repo = "test_repo"

			repo_dir = self._get_repo_dir(repo)
			ebuild_dir = os.path.join(repo_dir, a.cp)
			ebuild_path = os.path.join(ebuild_dir, a.cpv.split("/")[1] + ".ebuild")

			portdb = self.trees[self.eroot]["porttree"].dbapi
			tmpsettings['O'] = ebuild_dir
			if not digestgen(mysettings=tmpsettings, myportdb=portdb):
				raise AssertionError('digest creation failed for %s' % ebuild_path)

	def _create_binpkgs(self, binpkgs):
		# When using BUILD_ID, there can be mutiple instances for the
		# same cpv. Therefore, binpkgs may be an iterable instead of
		# a dict.
		items = getattr(binpkgs, 'items', None)
		items = items() if items is not None else binpkgs
		for cpv, metadata in items:
			a = Atom("=" + cpv, allow_repo=True)
			repo = a.repo
			if repo is None:
				repo = "test_repo"

			pn = catsplit(a.cp)[1]
			cat, pf = catsplit(a.cpv)
			metadata = metadata.copy()
			metadata.setdefault("SLOT", "0")
			metadata.setdefault("KEYWORDS", "x86")
			metadata.setdefault("BUILD_TIME", "0")
			metadata["repository"] = repo
			metadata["CATEGORY"] = cat
			metadata["PF"] = pf

			repo_dir = self.pkgdir
			category_dir = os.path.join(repo_dir, cat)
			if "BUILD_ID" in metadata:
				binpkg_path = os.path.join(category_dir, pn,
					"%s-%s.xpak"% (pf, metadata["BUILD_ID"]))
			else:
				binpkg_path = os.path.join(category_dir, pf + ".tbz2")

			ensure_dirs(os.path.dirname(binpkg_path))
			t = portage.xpak.tbz2(binpkg_path)
			t.recompose_mem(portage.xpak.xpak_mem(metadata))

	def _create_installed(self, installed):
		for cpv in installed:
			a = Atom("=" + cpv, allow_repo=True)
			repo = a.repo
			if repo is None:
				repo = "test_repo"

			vdb_pkg_dir = os.path.join(self.vdbdir, a.cpv)
			try:
				os.makedirs(vdb_pkg_dir)
			except os.error:
				pass

			metadata = installed[cpv].copy()
			metadata.setdefault("SLOT", "0")
			metadata.setdefault("BUILD_TIME", "0")
			metadata.setdefault("COUNTER", "0")
			metadata.setdefault("KEYWORDS", "~x86")

			unknown_keys = set(metadata).difference(
				portage.dbapi.dbapi._known_keys)
			unknown_keys.discard("BUILD_TIME")
			unknown_keys.discard("BUILD_ID")
			unknown_keys.discard("COUNTER")
			unknown_keys.discard("repository")
			unknown_keys.discard("USE")
			unknown_keys.discard("PROVIDES")
			unknown_keys.discard("REQUIRES")
			if unknown_keys:
				raise ValueError("metadata of installed '%s' contains unknown keys: %s" %
					(cpv, sorted(unknown_keys)))

			metadata["repository"] = repo
			for k, v in metadata.items():
				with open(os.path.join(vdb_pkg_dir, k), "w") as f:
					f.write("%s\n" % v)

			ebuild_path = os.path.join(vdb_pkg_dir, a.cpv.split("/")[1] + ".ebuild")
			with open(ebuild_path, "w") as f:
				f.write('EAPI="%s"\n' % metadata.pop('EAPI', '0'))
				for k, v in metadata.items():
					f.write('%s="%s"\n' % (k, v))

			env_path = os.path.join(vdb_pkg_dir, 'environment.bz2')
			with bz2.BZ2File(env_path, mode='w') as f:
				with open(ebuild_path, 'rb') as inputfile:
					f.write(inputfile.read())

	def _create_profile(self, ebuilds, eclasses, installed, profile, repo_configs, user_config, sets):

		user_config_dir = os.path.join(self.eroot, USER_CONFIG_PATH)

		try:
			os.makedirs(user_config_dir)
		except os.error:
			pass

		for repo in self._repositories:
			if repo == "DEFAULT":
				continue

			repo_dir = self._get_repo_dir(repo)
			profile_dir = os.path.join(repo_dir, "profiles")
			metadata_dir = os.path.join(repo_dir, "metadata")
			os.makedirs(metadata_dir)

			#Create $REPO/profiles/categories
			categories = set()
			for cpv in ebuilds:
				ebuilds_repo = Atom("="+cpv, allow_repo=True).repo
				if ebuilds_repo is None:
					ebuilds_repo = "test_repo"
				if ebuilds_repo == repo:
					categories.add(catsplit(cpv)[0])

			categories_file = os.path.join(profile_dir, "categories")
			with open(categories_file, "w") as f:
				for cat in categories:
					f.write(cat + "\n")

			#Create $REPO/profiles/license_groups
			license_file = os.path.join(profile_dir, "license_groups")
			with open(license_file, "w") as f:
				f.write("EULA TEST\n")

			repo_config = repo_configs.get(repo)
			if repo_config:
				for config_file, lines in repo_config.items():
					if config_file not in self.config_files and not any(fnmatch.fnmatch(config_file, os.path.join(x, "*")) for x in self.config_files):
						raise ValueError("Unknown config file: '%s'" % config_file)

					if config_file in ("layout.conf",):
						file_name = os.path.join(repo_dir, "metadata", config_file)
					else:
						file_name = os.path.join(profile_dir, config_file)
						if "/" in config_file and not os.path.isdir(os.path.dirname(file_name)):
							os.makedirs(os.path.dirname(file_name))
					with open(file_name, "w") as f:
						for line in lines:
							f.write("%s\n" % line)
						# Temporarily write empty value of masters until it becomes default.
						# TODO: Delete all references to "# use implicit masters" when empty value becomes default.
						if config_file == "layout.conf" and not any(line.startswith(("masters =", "# use implicit masters")) for line in lines):
							f.write("masters =\n")

			#Create $profile_dir/eclass (we fail to digest the ebuilds if it's not there)
			eclass_dir = os.path.join(repo_dir, "eclass")
			os.makedirs(eclass_dir)

			for eclass_name, eclass_content in eclasses.items():
				with open(os.path.join(eclass_dir, "{}.eclass".format(eclass_name)), 'wt') as f:
					if isinstance(eclass_content, str):
						eclass_content = [eclass_content]
					for line in eclass_content:
						f.write("{}\n".format(line))

			# Temporarily write empty value of masters until it becomes default.
			if not repo_config or "layout.conf" not in repo_config:
				layout_conf_path = os.path.join(repo_dir, "metadata", "layout.conf")
				with open(layout_conf_path, "w") as f:
					f.write("masters =\n")

			if repo == "test_repo":
				#Create a minimal profile in /var/db/repos/gentoo
				sub_profile_dir = os.path.join(profile_dir, "default", "linux", "x86", "test_profile")
				os.makedirs(sub_profile_dir)

				if not (profile and "eapi" in profile):
					eapi_file = os.path.join(sub_profile_dir, "eapi")
					with open(eapi_file, "w") as f:
						f.write("0\n")

				make_defaults_file = os.path.join(sub_profile_dir, "make.defaults")
				with open(make_defaults_file, "w") as f:
					f.write("ARCH=\"x86\"\n")
					f.write("ACCEPT_KEYWORDS=\"x86\"\n")

				use_force_file = os.path.join(sub_profile_dir, "use.force")
				with open(use_force_file, "w") as f:
					f.write("x86\n")

				parent_file = os.path.join(sub_profile_dir, "parent")
				with open(parent_file, "w") as f:
					f.write("..\n")

				if profile:
					for config_file, lines in profile.items():
						if config_file not in self.config_files:
							raise ValueError("Unknown config file: '%s'" % config_file)

						file_name = os.path.join(sub_profile_dir, config_file)
						with open(file_name, "w") as f:
							for line in lines:
								f.write("%s\n" % line)

				#Create profile symlink
				os.symlink(sub_profile_dir, os.path.join(user_config_dir, "make.profile"))

		make_conf = {
			"ACCEPT_KEYWORDS": "x86",
			"CLEAN_DELAY": "0",
			"DISTDIR" : self.distdir,
			"EMERGE_WARNING_DELAY": "0",
			"PKGDIR": self.pkgdir,
			"PORTAGE_INST_GID": str(portage.data.portage_gid),
			"PORTAGE_INST_UID": str(portage.data.portage_uid),
			"PORTAGE_TMPDIR": os.path.join(self.eroot, 'var/tmp'),
		}

		if os.environ.get("NOCOLOR"):
			make_conf["NOCOLOR"] = os.environ["NOCOLOR"]

		# Pass along PORTAGE_USERNAME and PORTAGE_GRPNAME since they
		# need to be inherited by ebuild subprocesses.
		if 'PORTAGE_USERNAME' in os.environ:
			make_conf['PORTAGE_USERNAME'] = os.environ['PORTAGE_USERNAME']
		if 'PORTAGE_GRPNAME' in os.environ:
			make_conf['PORTAGE_GRPNAME'] = os.environ['PORTAGE_GRPNAME']

		make_conf_lines = []
		for k_v in make_conf.items():
			make_conf_lines.append('%s="%s"' % k_v)

		if "make.conf" in user_config:
			make_conf_lines.extend(user_config["make.conf"])

		if not portage.process.sandbox_capable or \
			os.environ.get("SANDBOX_ON") == "1":
			# avoid problems from nested sandbox instances
			make_conf_lines.append('FEATURES="${FEATURES} -sandbox -usersandbox"')

		configs = user_config.copy()
		configs["make.conf"] = make_conf_lines

		for config_file, lines in configs.items():
			if config_file not in self.config_files:
				raise ValueError("Unknown config file: '%s'" % config_file)

			file_name = os.path.join(user_config_dir, config_file)
			with open(file_name, "w") as f:
				for line in lines:
					f.write("%s\n" % line)

		#Create /usr/share/portage/config/make.globals
		make_globals_path = os.path.join(self.eroot,
			GLOBAL_CONFIG_PATH.lstrip(os.sep), "make.globals")
		ensure_dirs(os.path.dirname(make_globals_path))
		os.symlink(os.path.join(cnf_path, "make.globals"),
			make_globals_path)

		#Create /usr/share/portage/config/sets/portage.conf
		default_sets_conf_dir = os.path.join(self.eroot, "usr/share/portage/config/sets")

		try:
			os.makedirs(default_sets_conf_dir)
		except os.error:
			pass

		provided_sets_portage_conf = (
			os.path.join(cnf_path, "sets", "portage.conf"))
		os.symlink(provided_sets_portage_conf, os.path.join(default_sets_conf_dir, "portage.conf"))

		set_config_dir = os.path.join(user_config_dir, "sets")

		try:
			os.makedirs(set_config_dir)
		except os.error:
			pass

		for sets_file, lines in sets.items():
			file_name = os.path.join(set_config_dir, sets_file)
			with open(file_name, "w") as f:
				for line in lines:
					f.write("%s\n" % line)

		if cnf_path_repoman is not None:
			#Create /usr/share/repoman
			repoman_share_dir = os.path.join(self.eroot, 'usr', 'share', 'repoman')
			os.symlink(cnf_path_repoman, repoman_share_dir)

	def _create_world(self, world, world_sets):
		#Create /var/lib/portage/world
		var_lib_portage = os.path.join(self.eroot, "var", "lib", "portage")
		os.makedirs(var_lib_portage)

		world_file = os.path.join(var_lib_portage, "world")
		world_set_file = os.path.join(var_lib_portage, "world_sets")

		with open(world_file, "w") as f:
			for atom in world:
				f.write("%s\n" % atom)

		with open(world_set_file, "w") as f:
			for atom in world_sets:
				f.write("%s\n" % atom)

	def _load_config(self):

		create_trees_kwargs = {}
		if self.target_root != os.sep:
			create_trees_kwargs["target_root"] = self.target_root

		env = {
			"PORTAGE_REPOSITORIES": "\n".join("[%s]\n%s" % (repo_name, "\n".join("%s = %s" % (k, v) for k, v in repo_config.items())) for repo_name, repo_config in self._repositories.items())
		}

		if self.debug:
			env["PORTAGE_DEBUG"] = "1"

		trees = portage.create_trees(env=env, eprefix=self.eprefix,
			**create_trees_kwargs)

		for root, root_trees in trees.items():
			settings = root_trees["vartree"].settings
			settings._init_dirs()
			setconfig = load_default_config(settings, root_trees)
			root_trees["root_config"] = RootConfig(settings, root_trees, setconfig)

		return trees[trees._target_eroot]["vartree"].settings, trees

	def run(self, atoms, options={}, action=None):
		options = options.copy()
		options["--pretend"] = True
		if self.debug:
			options["--debug"] = True

		if action is None:
			if options.get("--depclean"):
				action = "depclean"
			elif options.get("--prune"):
				action = "prune"

		if "--usepkgonly" in options:
			options["--usepkg"] = True

		global_noiselimit = portage.util.noiselimit
		global_emergelog_disable = _emerge.emergelog._disable
		try:

			if not self.debug:
				portage.util.noiselimit = -2
			_emerge.emergelog._disable = True

			if action in ("depclean", "prune"):
				depclean_result = _calc_depclean(self.settings, self.trees, None,
					options, action, InternalPackageSet(initial_atoms=atoms, allow_wildcard=True), None)
				result = ResolverPlaygroundDepcleanResult(
					atoms,
					depclean_result.returncode,
					depclean_result.cleanlist,
					depclean_result.ordered,
					depclean_result.req_pkg_count,
					depclean_result.depgraph,
				)
			else:
				params = create_depgraph_params(options, action)
				success, depgraph, favorites = backtrack_depgraph(
					self.settings, self.trees, options, params, action, atoms, None)
				depgraph._show_merge_list()
				depgraph.display_problems()
				result = ResolverPlaygroundResult(atoms, success, depgraph, favorites)
		finally:
			portage.util.noiselimit = global_noiselimit
			_emerge.emergelog._disable = global_emergelog_disable

		return result

	def run_TestCase(self, test_case):
		if not isinstance(test_case, ResolverPlaygroundTestCase):
			raise TypeError("ResolverPlayground needs a ResolverPlaygroundTestCase")
		for atoms in test_case.requests:
			result = self.run(atoms, test_case.options, test_case.action)
			if not test_case.compare_with_result(result):
				return

	def cleanup(self):
		for eroot in self.trees:
			portdb = self.trees[eroot]["porttree"].dbapi
			portdb.close_caches()
		if self.debug:
			print("\nEROOT=%s" % self.eroot)
		else:
			shutil.rmtree(self.eroot)
		if hasattr(self, '_orig_eprefix'):
			portage.const.EPREFIX = self._orig_eprefix


class ResolverPlaygroundTestCase:

	def __init__(self, request, **kwargs):
		self.all_permutations = kwargs.pop("all_permutations", False)
		self.ignore_mergelist_order = kwargs.pop("ignore_mergelist_order", False)
		self.ignore_cleanlist_order = kwargs.pop("ignore_cleanlist_order", False)
		self.ambiguous_merge_order = kwargs.pop("ambiguous_merge_order", False)
		self.ambiguous_slot_collision_solutions = kwargs.pop("ambiguous_slot_collision_solutions", False)
		self.check_repo_names = kwargs.pop("check_repo_names", False)
		self.merge_order_assertions = kwargs.pop("merge_order_assertions", False)

		if self.all_permutations:
			self.requests = list(permutations(request))
		else:
			self.requests = [request]

		self.options = kwargs.pop("options", {})
		self.action = kwargs.pop("action", None)
		self.test_success = True
		self.fail_msg = None
		self._checks = kwargs.copy()

	def compare_with_result(self, result):
		checks = dict.fromkeys(result.checks)
		for key, value in self._checks.items():
			if not key in checks:
				raise KeyError("Not an available check: '%s'" % key)
			checks[key] = value

		fail_msgs = []
		for key, value in checks.items():
			got = getattr(result, key)
			expected = value

			if key in result.optional_checks and expected is None:
				continue

			if key == "mergelist":
				if not self.check_repo_names:
					#Strip repo names if we don't check them
					if got:
						new_got = []
						for cpv in got:
							if cpv[:1] == "!":
								new_got.append(cpv)
								continue
							new_got.append(cpv.split(_repo_separator)[0])
						got = new_got
					if expected:
						new_expected = []
						for obj in expected:
							if isinstance(obj, str):
								if obj[:1] == "!":
									new_expected.append(obj)
									continue
								new_expected.append(
									obj.split(_repo_separator)[0])
								continue
							new_expected.append(set())
							for cpv in obj:
								if cpv[:1] != "!":
									cpv = cpv.split(_repo_separator)[0]
								new_expected[-1].add(cpv)
						expected = new_expected
				if self.ignore_mergelist_order and got is not None:
					got = set(got)
					expected = set(expected)

				if self.ambiguous_merge_order and got:
					expected_stack = list(reversed(expected))
					got_stack = list(reversed(got))
					new_expected = []
					match = True
					while got_stack and expected_stack:
						got_token = got_stack.pop()
						expected_obj = expected_stack.pop()
						if isinstance(expected_obj, str):
							new_expected.append(expected_obj)
							if got_token == expected_obj:
								continue
							# result doesn't match, so stop early
							match = False
							break
						expected_obj = set(expected_obj)
						try:
							expected_obj.remove(got_token)
						except KeyError:
							# result doesn't match, so stop early
							match = False
							break
						new_expected.append(got_token)
						while got_stack and expected_obj:
							got_token = got_stack.pop()
							try:
								expected_obj.remove(got_token)
							except KeyError:
								match = False
								break
							new_expected.append(got_token)
						if not match:
							# result doesn't match, so stop early
							break
						if expected_obj:
							# result does not match, so stop early
							match = False
							new_expected.append(tuple(expected_obj))
							break
					if expected_stack:
						# result does not match, add leftovers to new_expected
						match = False
						expected_stack.reverse()
						new_expected.extend(expected_stack)
					expected = new_expected

					if match and self.merge_order_assertions:
						for node1, node2 in self.merge_order_assertions:
							if not got.index(node1) < got.index(node2):
								fail_msgs.append("atoms: (" + \
									", ".join(result.atoms) + "), key: " + \
									("merge_order_assertions, expected: %s" % \
									str((node1, node2))) + \
									", got: " + str(got))

			elif key == "cleanlist" and self.ignore_cleanlist_order:
				got = set(got)
				expected = set(expected)

			elif key == "slot_collision_solutions" and \
				self.ambiguous_slot_collision_solutions:
				# Tests that use all_permutations can have multiple
				# outcomes here.
				for x in expected:
					if x == got:
						expected = x
						break
			elif key in ("unstable_keywords", "needed_p_mask_changes",
				"unsatisfied_deps", "required_use_unsatisfied") and \
				expected is not None:
				expected = set(expected)

			elif key == "forced_rebuilds" and expected is not None:
				expected = dict((k, set(v)) for k, v in expected.items())

			if got != expected:
				fail_msgs.append("atoms: (" + ", ".join(result.atoms) + "), key: " + \
					key + ", expected: " + str(expected) + ", got: " + str(got))
		if fail_msgs:
			self.test_success = False
			self.fail_msg = "\n".join(fail_msgs)
			return False
		return True


def _mergelist_str(x, depgraph):
	if isinstance(x, DependencyArg):
		mergelist_str = x.arg
	elif isinstance(x, Blocker):
		mergelist_str = x.atom
	else:
		repo_str = ""
		if x.repo != "test_repo":
			repo_str = _repo_separator + x.repo
		build_id_str = ""
		if (x.type_name == "binary" and
			x.cpv.build_id is not None):
			build_id_str = "-%s" % x.cpv.build_id
		mergelist_str = x.cpv + build_id_str + repo_str
		if x.built:
			if x.operation == "merge":
				desc = x.type_name
			else:
				desc = x.operation
			mergelist_str = "[%s]%s" % (desc, mergelist_str)
		if x.root != depgraph._frozen_config._running_root.root:
			mergelist_str += "{targetroot}"
	return mergelist_str


class ResolverPlaygroundResult:

	checks = (
		"success", "mergelist", "use_changes", "license_changes",
		"unstable_keywords", "slot_collision_solutions",
		"circular_dependency_solutions", "needed_p_mask_changes",
		"unsatisfied_deps", "forced_rebuilds", "required_use_unsatisfied",
		"graph_order",
		)
	optional_checks = (
		"forced_rebuilds",
		"required_use_unsatisfied",
		"unsatisfied_deps",
		"graph_order",
		)

	def __init__(self, atoms, success, mydepgraph, favorites):
		self.atoms = atoms
		self.success = success
		self.depgraph = mydepgraph
		self.favorites = favorites
		self.mergelist = None
		self.use_changes = None
		self.license_changes = None
		self.unstable_keywords = None
		self.needed_p_mask_changes = None
		self.slot_collision_solutions = None
		self.circular_dependency_solutions = None
		self.unsatisfied_deps = frozenset()
		self.forced_rebuilds = None
		self.required_use_unsatisfied = None

		self.graph_order = [_mergelist_str(node, self.depgraph) for node in self.depgraph._dynamic_config.digraph]

		if self.depgraph._dynamic_config._serialized_tasks_cache is not None:
			self.mergelist = []
			for x in self.depgraph._dynamic_config._serialized_tasks_cache:
				self.mergelist.append(_mergelist_str(x, self.depgraph))

		if self.depgraph._dynamic_config._needed_use_config_changes:
			self.use_changes = {}
			for pkg, needed_use_config_changes in \
				self.depgraph._dynamic_config._needed_use_config_changes.items():
				new_use, changes = needed_use_config_changes
				self.use_changes[pkg.cpv] = changes

		if self.depgraph._dynamic_config._needed_unstable_keywords:
			self.unstable_keywords = set()
			for pkg in self.depgraph._dynamic_config._needed_unstable_keywords:
				self.unstable_keywords.add(pkg.cpv)

		if self.depgraph._dynamic_config._needed_p_mask_changes:
			self.needed_p_mask_changes = set()
			for pkg in self.depgraph._dynamic_config._needed_p_mask_changes:
				self.needed_p_mask_changes.add(pkg.cpv)

		if self.depgraph._dynamic_config._needed_license_changes:
			self.license_changes = {}
			for pkg, missing_licenses in self.depgraph._dynamic_config._needed_license_changes.items():
				self.license_changes[pkg.cpv] = missing_licenses

		if self.depgraph._dynamic_config._slot_conflict_handler is not None:
			self.slot_collision_solutions = []
			handler = self.depgraph._dynamic_config._slot_conflict_handler

			for change in handler.changes:
				new_change = {}
				for pkg in change:
					new_change[pkg.cpv] = change[pkg]
				self.slot_collision_solutions.append(new_change)

		if self.depgraph._dynamic_config._circular_dependency_handler is not None:
			handler = self.depgraph._dynamic_config._circular_dependency_handler
			sol = handler.solutions
			self.circular_dependency_solutions = dict(zip([x.cpv for x in sol.keys()], sol.values()))

		if self.depgraph._dynamic_config._unsatisfied_deps_for_display:
			self.unsatisfied_deps = set(dep_info[0][1]
				for dep_info in self.depgraph._dynamic_config._unsatisfied_deps_for_display)

		if self.depgraph._forced_rebuilds:
			self.forced_rebuilds = dict(
				(child.cpv, set(parent.cpv for parent in parents))
				for child_dict in self.depgraph._forced_rebuilds.values()
				for child, parents in child_dict.items())

		required_use_unsatisfied = []
		for pargs, kwargs in \
			self.depgraph._dynamic_config._unsatisfied_deps_for_display:
			if "show_req_use" in kwargs:
				required_use_unsatisfied.append(pargs[1])
		if required_use_unsatisfied:
			self.required_use_unsatisfied = set(required_use_unsatisfied)

class ResolverPlaygroundDepcleanResult:

	checks = (
		"success", "cleanlist", "ordered", "req_pkg_count",
		"graph_order",
		)
	optional_checks = (
		"ordered", "req_pkg_count",
		"graph_order",
		)

	def __init__(self, atoms, rval, cleanlist, ordered, req_pkg_count, depgraph):
		self.atoms = atoms
		self.success = rval == 0
		self.cleanlist = cleanlist
		self.ordered = ordered
		self.req_pkg_count = req_pkg_count
		self.graph_order = [_mergelist_str(node, depgraph) for node in depgraph._dynamic_config.digraph]
