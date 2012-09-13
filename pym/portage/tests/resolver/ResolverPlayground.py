# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import permutations
import sys
import tempfile
import portage
from portage import os
from portage import shutil
from portage.const import (GLOBAL_CONFIG_PATH, PORTAGE_BASE_PATH,
	USER_CONFIG_PATH)
from portage.dep import Atom, _repo_separator
from portage.package.ebuild.config import config
from portage.package.ebuild.digestgen import digestgen
from portage._sets import load_default_config
from portage._sets.base import InternalPackageSet
from portage.util import ensure_dirs, normalize_path
from portage.versions import catsplit

import _emerge
from _emerge.actions import calc_depclean
from _emerge.Blocker import Blocker
from _emerge.create_depgraph_params import create_depgraph_params
from _emerge.depgraph import backtrack_depgraph
from _emerge.RootConfig import RootConfig

if sys.hexversion >= 0x3000000:
	basestring = str

class ResolverPlayground(object):
	"""
	This class helps to create the necessary files on disk and
	the needed settings instances, etc. for the resolver to do
	its work.
	"""

	config_files = frozenset(("eapi", "make.conf", "package.accept_keywords", "package.use",
		"package.use.stable.mask", "package.mask", "package.keywords",
		"package.unmask", "package.properties", "package.license", "use.mask", "use.force",
		"layout.conf",))

	metadata_xml_template = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "http://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
<herd>%(herd)s</herd>
<maintainer>
<email>maintainer-needed@gentoo.org</email>
<description>Description of the maintainership</description>
</maintainer>
<longdescription>Long description of the package</longdescription>
<use>
%(flags)s
</use>
</pkgmetadata>
"""

	def __init__(self, ebuilds={}, binpkgs={}, installed={}, profile={}, repo_configs={}, \
		user_config={}, sets={}, world=[], world_sets=[], distfiles={}, debug=False):
		"""
		ebuilds: cpv -> metadata mapping simulating available ebuilds. 
		installed: cpv -> metadata mapping simulating installed packages.
			If a metadata key is missing, it gets a default value.
		profile: settings defined by the profile.
		"""
		self.debug = debug
		self.eprefix = normalize_path(tempfile.mkdtemp())
		self.eroot = self.eprefix + os.sep
		self.distdir = os.path.join(self.eroot, "var", "portage", "distfiles")
		self.pkgdir = os.path.join(self.eprefix, "pkgdir")
		self.portdir = os.path.join(self.eroot, "usr/portage")
		self.vdbdir = os.path.join(self.eroot, "var/db/pkg")
		os.makedirs(self.portdir)
		os.makedirs(self.vdbdir)

		if not debug:
			portage.util.noiselimit = -2

		self.repo_dirs = {}
		#Make sure the main repo is always created
		self._get_repo_dir("test_repo")

		self._create_distfiles(distfiles)
		self._create_ebuilds(ebuilds)
		self._create_binpkgs(binpkgs)
		self._create_installed(installed)
		self._create_profile(ebuilds, installed, profile, repo_configs, user_config, sets)
		self._create_world(world, world_sets)

		self.settings, self.trees = self._load_config()

		self._create_ebuild_manifests(ebuilds)
		
		portage.util.noiselimit = 0

	def _get_repo_dir(self, repo):
		"""
		Create the repo directory if needed.
		"""
		if repo not in self.repo_dirs:
			if repo == "test_repo":
				repo_path = self.portdir
			else:
				repo_path = os.path.join(self.eroot, "usr", "local", repo)

			self.repo_dirs[repo] = repo_path
			profile_path = os.path.join(repo_path, "profiles")

			try:
				os.makedirs(profile_path)
			except os.error:
				pass

			repo_name_file = os.path.join(profile_path, "repo_name")
			f = open(repo_name_file, "w")
			f.write("%s\n" % repo)
			f.close()

		return self.repo_dirs[repo]

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
			desc = metadata.pop("DESCRIPTION", None)
			eapi = metadata.pop("EAPI", 0)
			lic = metadata.pop("LICENSE", "")
			properties = metadata.pop("PROPERTIES", "")
			slot = metadata.pop("SLOT", 0)
			keywords = metadata.pop("KEYWORDS", "x86")
			homepage = metadata.pop("HOMEPAGE", None)
			src_uri = metadata.pop("SRC_URI", None)
			iuse = metadata.pop("IUSE", "")
			provide = metadata.pop("PROVIDE", None)
			depend = metadata.pop("DEPEND", "")
			rdepend = metadata.pop("RDEPEND", None)
			pdepend = metadata.pop("PDEPEND", None)
			required_use = metadata.pop("REQUIRED_USE", None)
			misc_content = metadata.pop("MISC_CONTENT", None)

			if metadata:
				raise ValueError("metadata of ebuild '%s' contains unknown keys: %s" % (cpv, metadata.keys()))

			repo_dir = self._get_repo_dir(repo)
			ebuild_dir = os.path.join(repo_dir, a.cp)
			ebuild_path = os.path.join(ebuild_dir, a.cpv.split("/")[1] + ".ebuild")
			try:
				os.makedirs(ebuild_dir)
			except os.error:
				pass

			f = open(ebuild_path, "w")
			if copyright_header is not None:
				f.write(copyright_header)
			f.write('EAPI="' + str(eapi) + '"\n')
			if desc is not None:
				f.write('DESCRIPTION="%s"\n' % desc)
			if homepage is not None:
				f.write('HOMEPAGE="%s"\n' % homepage)
			if src_uri is not None:
				f.write('SRC_URI="%s"\n' % src_uri)
			f.write('LICENSE="' + str(lic) + '"\n')
			f.write('PROPERTIES="' + str(properties) + '"\n')
			f.write('SLOT="' + str(slot) + '"\n')
			f.write('KEYWORDS="' + str(keywords) + '"\n')
			f.write('IUSE="' + str(iuse) + '"\n')
			if provide is not None:
				f.write('PROVIDE="%s"\n' % provide)
			f.write('DEPEND="' + str(depend) + '"\n')
			if rdepend is not None:
				f.write('RDEPEND="' + str(rdepend) + '"\n')
			if pdepend is not None:
				f.write('PDEPEND="' + str(pdepend) + '"\n')
			if required_use is not None:
				f.write('REQUIRED_USE="' + str(required_use) + '"\n')
			if misc_content is not None:
				f.write(misc_content)
			f.close()

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
		for cpv, metadata in binpkgs.items():
			a = Atom("=" + cpv, allow_repo=True)
			repo = a.repo
			if repo is None:
				repo = "test_repo"

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
			binpkg_path = os.path.join(category_dir, pf + ".tbz2")
			ensure_dirs(category_dir)
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
			eapi = metadata.pop("EAPI", 0)
			lic = metadata.pop("LICENSE", "")
			properties = metadata.pop("PROPERTIES", "")
			slot = metadata.pop("SLOT", 0)
			build_time = metadata.pop("BUILD_TIME", "0")
			keywords = metadata.pop("KEYWORDS", "~x86")
			iuse = metadata.pop("IUSE", "")
			use = metadata.pop("USE", "")
			provide = metadata.pop("PROVIDE", None)
			depend = metadata.pop("DEPEND", "")
			rdepend = metadata.pop("RDEPEND", None)
			pdepend = metadata.pop("PDEPEND", None)
			required_use = metadata.pop("REQUIRED_USE", None)

			if metadata:
				raise ValueError("metadata of installed '%s' contains unknown keys: %s" % (cpv, metadata.keys()))

			def write_key(key, value):
				f = open(os.path.join(vdb_pkg_dir, key), "w")
				f.write(str(value) + "\n")
				f.close()
			
			write_key("EAPI", eapi)
			write_key("BUILD_TIME", build_time)
			write_key("COUNTER", "0")
			write_key("LICENSE", lic)
			write_key("PROPERTIES", properties)
			write_key("SLOT", slot)
			write_key("LICENSE", lic)
			write_key("PROPERTIES", properties)
			write_key("repository", repo)
			write_key("KEYWORDS", keywords)
			write_key("IUSE", iuse)
			write_key("USE", use)
			if provide is not None:
				write_key("PROVIDE", provide)
			write_key("DEPEND", depend)
			if rdepend is not None:
				write_key("RDEPEND", rdepend)
			if pdepend is not None:
				write_key("PDEPEND", pdepend)
			if required_use is not None:
				write_key("REQUIRED_USE", required_use)

	def _create_profile(self, ebuilds, installed, profile, repo_configs, user_config, sets):

		user_config_dir = os.path.join(self.eroot, USER_CONFIG_PATH)

		try:
			os.makedirs(user_config_dir)
		except os.error:
			pass

		for repo in self.repo_dirs:
			repo_dir = self._get_repo_dir(repo)
			profile_dir = os.path.join(self._get_repo_dir(repo), "profiles")
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
			f = open(categories_file, "w")
			for cat in categories:
				f.write(cat + "\n")
			f.close()
			
			#Create $REPO/profiles/license_groups
			license_file = os.path.join(profile_dir, "license_groups")
			f = open(license_file, "w")
			f.write("EULA TEST\n")
			f.close()

			repo_config = repo_configs.get(repo) 
			if repo_config:
				for config_file, lines in repo_config.items():
					if config_file not in self.config_files:
						raise ValueError("Unknown config file: '%s'" % config_file)

					if config_file in ("layout.conf",):
						file_name = os.path.join(repo_dir, "metadata", config_file)
					else:
						file_name = os.path.join(profile_dir, config_file)
					f = open(file_name, "w")
					for line in lines:
						f.write("%s\n" % line)
					f.close()

			#Create $profile_dir/eclass (we fail to digest the ebuilds if it's not there)
			os.makedirs(os.path.join(repo_dir, "eclass"))

			if repo == "test_repo":
				#Create a minimal profile in /usr/portage
				sub_profile_dir = os.path.join(profile_dir, "default", "linux", "x86", "test_profile")
				os.makedirs(sub_profile_dir)

				if not (profile and "eapi" in profile):
					eapi_file = os.path.join(sub_profile_dir, "eapi")
					f = open(eapi_file, "w")
					f.write("0\n")
					f.close()

				make_defaults_file = os.path.join(sub_profile_dir, "make.defaults")
				f = open(make_defaults_file, "w")
				f.write("ARCH=\"x86\"\n")
				f.write("ACCEPT_KEYWORDS=\"x86\"\n")
				f.close()

				use_force_file = os.path.join(sub_profile_dir, "use.force")
				f = open(use_force_file, "w")
				f.write("x86\n")
				f.close()

				parent_file = os.path.join(sub_profile_dir, "parent")
				f = open(parent_file, "w")
				f.write("..\n")
				f.close()

				if profile:
					for config_file, lines in profile.items():
						if config_file not in self.config_files:
							raise ValueError("Unknown config file: '%s'" % config_file)

						file_name = os.path.join(sub_profile_dir, config_file)
						f = open(file_name, "w")
						for line in lines:
							f.write("%s\n" % line)
						f.close()

				#Create profile symlink
				os.symlink(sub_profile_dir, os.path.join(user_config_dir, "make.profile"))

				#Create minimal herds.xml
				herds_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE herds SYSTEM "http://www.gentoo.org/dtd/herds.dtd">
<?xml-stylesheet href="/xsl/herds.xsl" type="text/xsl" ?>
<?xml-stylesheet href="/xsl/guide.xsl" type="text/xsl" ?>
<herds>
<herd>
  <name>base-system</name>
  <email>base-system@gentoo.org</email>
  <description>Core system utilities and libraries.</description>
  <maintainer>
    <email>base-system@gentoo.orgg</email>
    <name>Base System</name>
    <role>Base System Maintainer</role>
  </maintainer>
</herd>
</herds>
"""
				with open(os.path.join(metadata_dir, "metadata.xml"), 'w') as f:
					f.write(herds_xml)

		# Write empty entries for each repository, in order to exercise
		# RepoConfigLoader's repos.conf processing.
		repos_conf_file = os.path.join(user_config_dir, "repos.conf")		
		f = open(repos_conf_file, "w")
		for repo in sorted(self.repo_dirs.keys()):
			f.write("[%s]\n" % repo)
			f.write("\n")
		f.close()

		for config_file, lines in user_config.items():
			if config_file not in self.config_files:
				raise ValueError("Unknown config file: '%s'" % config_file)

			file_name = os.path.join(user_config_dir, config_file)
			f = open(file_name, "w")
			for line in lines:
				f.write("%s\n" % line)
			f.close()

		#Create /usr/share/portage/config/make.globals
		make_globals_path = os.path.join(self.eroot,
			GLOBAL_CONFIG_PATH.lstrip(os.sep), "make.globals")
		ensure_dirs(os.path.dirname(make_globals_path))
		os.symlink(os.path.join(PORTAGE_BASE_PATH, "cnf", "make.globals"),
			make_globals_path)

		#Create /usr/share/portage/config/sets/portage.conf
		default_sets_conf_dir = os.path.join(self.eroot, "usr/share/portage/config/sets")
		
		try:
			os.makedirs(default_sets_conf_dir)
		except os.error:
			pass

		provided_sets_portage_conf = \
			os.path.join(PORTAGE_BASE_PATH, "cnf/sets/portage.conf")
		os.symlink(provided_sets_portage_conf, os.path.join(default_sets_conf_dir, "portage.conf"))

		set_config_dir = os.path.join(user_config_dir, "sets")

		try:
			os.makedirs(set_config_dir)
		except os.error:
			pass

		for sets_file, lines in sets.items():
			file_name = os.path.join(set_config_dir, sets_file)
			f = open(file_name, "w")
			for line in lines:
				f.write("%s\n" % line)
			f.close()

		user_config_dir = os.path.join(self.eroot, "etc", "portage")

		try:
			os.makedirs(user_config_dir)
		except os.error:
			pass

		for config_file, lines in user_config.items():
			if config_file not in self.config_files:
				raise ValueError("Unknown config file: '%s'" % config_file)

			file_name = os.path.join(user_config_dir, config_file)
			f = open(file_name, "w")
			for line in lines:
				f.write("%s\n" % line)
			f.close()

	def _create_world(self, world, world_sets):
		#Create /var/lib/portage/world
		var_lib_portage = os.path.join(self.eroot, "var", "lib", "portage")
		os.makedirs(var_lib_portage)

		world_file = os.path.join(var_lib_portage, "world")
		world_set_file = os.path.join(var_lib_portage, "world_sets")

		f = open(world_file, "w")
		for atom in world:
			f.write("%s\n" % atom)
		f.close()

		f = open(world_set_file, "w")
		for atom in world_sets:
			f.write("%s\n" % atom)
		f.close()

	def _load_config(self):
		portdir_overlay = []
		for repo_name in sorted(self.repo_dirs):
			path = self.repo_dirs[repo_name]
			if path != self.portdir:
				portdir_overlay.append(path)

		env = {
			"ACCEPT_KEYWORDS": "x86",
			"DISTDIR" : self.distdir,
			"PKGDIR": self.pkgdir,
			"PORTDIR": self.portdir,
			"PORTDIR_OVERLAY": " ".join(portdir_overlay),
			'PORTAGE_TMPDIR'       : os.path.join(self.eroot, 'var/tmp'),
		}

		if os.environ.get("NOCOLOR"):
			env["NOCOLOR"] = os.environ["NOCOLOR"]

		if os.environ.get("SANDBOX_ON") == "1":
			# avoid problems from nested sandbox instances
			env["FEATURES"] = "-sandbox"

		# Pass along PORTAGE_USERNAME and PORTAGE_GRPNAME since they
		# need to be inherited by ebuild subprocesses.
		if 'PORTAGE_USERNAME' in os.environ:
			env['PORTAGE_USERNAME'] = os.environ['PORTAGE_USERNAME']
		if 'PORTAGE_GRPNAME' in os.environ:
			env['PORTAGE_GRPNAME'] = os.environ['PORTAGE_GRPNAME']

		trees = portage.create_trees(env=env, eprefix=self.eprefix)
		for root, root_trees in trees.items():
			settings = root_trees["vartree"].settings
			settings._init_dirs()
			setconfig = load_default_config(settings, root_trees)
			root_trees["root_config"] = RootConfig(settings, root_trees, setconfig)
		
		return settings, trees

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
				rval, cleanlist, ordered, req_pkg_count = \
					calc_depclean(self.settings, self.trees, None,
					options, action, InternalPackageSet(initial_atoms=atoms, allow_wildcard=True), None)
				result = ResolverPlaygroundDepcleanResult( \
					atoms, rval, cleanlist, ordered, req_pkg_count)
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
		portdb = self.trees[self.eroot]["porttree"].dbapi
		portdb.close_caches()
		portage.dbapi.porttree.portdbapi.portdbapi_instances.remove(portdb)
		if self.debug:
			print("\nEROOT=%s" % self.eroot)
		else:
			shutil.rmtree(self.eroot)

class ResolverPlaygroundTestCase(object):

	def __init__(self, request, **kwargs):
		self.all_permutations = kwargs.pop("all_permutations", False)
		self.ignore_mergelist_order = kwargs.pop("ignore_mergelist_order", False)
		self.ambiguous_merge_order = kwargs.pop("ambiguous_merge_order", False)
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
							if isinstance(obj, basestring):
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
						if isinstance(expected_obj, basestring):
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
							if not (got.index(node1) < got.index(node2)):
								fail_msgs.append("atoms: (" + \
									", ".join(result.atoms) + "), key: " + \
									("merge_order_assertions, expected: %s" % \
									str((node1, node2))) + \
									", got: " + str(got))

			elif key in ("unstable_keywords", "needed_p_mask_changes") and expected is not None:
				expected = set(expected)

			if got != expected:
				fail_msgs.append("atoms: (" + ", ".join(result.atoms) + "), key: " + \
					key + ", expected: " + str(expected) + ", got: " + str(got))
		if fail_msgs:
			self.test_success = False
			self.fail_msg = "\n".join(fail_msgs)
			return False
		return True

class ResolverPlaygroundResult(object):

	checks = (
		"success", "mergelist", "use_changes", "license_changes", "unstable_keywords", "slot_collision_solutions",
		"circular_dependency_solutions", "needed_p_mask_changes",
		)
	optional_checks = (
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

		if self.depgraph._dynamic_config._serialized_tasks_cache is not None:
			self.mergelist = []
			for x in self.depgraph._dynamic_config._serialized_tasks_cache:
				if isinstance(x, Blocker):
					self.mergelist.append(x.atom)
				else:
					repo_str = ""
					if x.metadata["repository"] != "test_repo":
						repo_str = _repo_separator + x.metadata["repository"]
					mergelist_str = x.cpv + repo_str
					if x.built:
						if x.operation == "merge":
							desc = x.type_name
						else:
							desc = x.operation
						mergelist_str = "[%s]%s" % (desc, mergelist_str)
					self.mergelist.append(mergelist_str)

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
			self.slot_collision_solutions  = []
			handler = self.depgraph._dynamic_config._slot_conflict_handler

			for change in handler.changes:
				new_change = {}
				for pkg in change:
					new_change[pkg.cpv] = change[pkg]
				self.slot_collision_solutions.append(new_change)

		if self.depgraph._dynamic_config._circular_dependency_handler is not None:
			handler = self.depgraph._dynamic_config._circular_dependency_handler
			sol = handler.solutions
			self.circular_dependency_solutions = dict( zip([x.cpv for x in sol.keys()], sol.values()) )

class ResolverPlaygroundDepcleanResult(object):

	checks = (
		"success", "cleanlist", "ordered", "req_pkg_count",
		)
	optional_checks = (
		"ordered", "req_pkg_count",
		)

	def __init__(self, atoms, rval, cleanlist, ordered, req_pkg_count):
		self.atoms = atoms
		self.success = rval == 0
		self.cleanlist = cleanlist
		self.ordered = ordered
		self.req_pkg_count = req_pkg_count
