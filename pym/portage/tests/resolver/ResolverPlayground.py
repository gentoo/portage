# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import chain, permutations
import shutil
import tempfile
import portage
from portage import os
from portage.dbapi.vartree import vartree
from portage.dbapi.porttree import portagetree
from portage.dbapi.bintree import binarytree
from portage.dep import Atom
from portage.package.ebuild.config import config
from portage.sets import SetConfig
from portage.versions import catsplit

from _emerge.Blocker import Blocker
from _emerge.create_depgraph_params import create_depgraph_params
from _emerge.depgraph import backtrack_depgraph
from _emerge.RootConfig import RootConfig
from _emerge.main import setconfig_fallback

class ResolverPlayground(object):
	"""
	This class help to create the necessary files on disk and
	the needed settings instances, etc. for the resolver to do
	it's work.
	"""
	
	def __init__(self, ebuilds={}, installed={}, profile={}):
		"""
		ebuilds: cpv -> metadata mapping simulating avaiable ebuilds. 
		installed: cpv -> metadata mapping simulating installed packages.
			If a metadata key is missing, it gets a default value.
		profile: settings defined by the profile.
		"""
		self.root = tempfile.mkdtemp() + os.path.sep
		self.portdir = os.path.join(self.root, "usr/portage")
		self.vdbdir = os.path.join(self.root, "var/db/pkg")
		os.makedirs(self.portdir)
		os.makedirs(self.vdbdir)
		
		self._create_ebuilds(ebuilds)
		self._create_installed(installed)
		self._create_profile(ebuilds, installed, profile)
		
		self.settings, self.trees = self._load_config()
		
		self._create_ebuild_manifests(ebuilds)

	def _create_ebuilds(self, ebuilds):
		for cpv in ebuilds:
			a = Atom("=" + cpv)
			ebuild_dir = os.path.join(self.portdir, a.cp)
			ebuild_path = os.path.join(ebuild_dir, a.cpv.split("/")[1] + ".ebuild")
			try:
				os.makedirs(ebuild_dir)
			except os.error:
				pass
			
			metadata = ebuilds[cpv]
			eapi = metadata.get("EAPI", 0)
			slot = metadata.get("SLOT", 0)
			keywords = metadata.get("KEYWORDS", "x86")
			iuse = metadata.get("IUSE", "")
			depend = metadata.get("DEPEND", "")
			rdepend = metadata.get("RDEPEND", None)
			pdepend = metadata.get("PDEPEND", None)
			required_use = metadata.get("REQUIRED_USE", None)

			f = open(ebuild_path, "w")
			f.write('EAPI="' + str(eapi) + '"\n')
			f.write('SLOT="' + str(slot) + '"\n')
			f.write('KEYWORDS="' + str(keywords) + '"\n')
			f.write('IUSE="' + str(iuse) + '"\n')
			f.write('DEPEND="' + str(depend) + '"\n')
			if rdepend is not None:
				f.write('RDEPEND="' + str(rdepend) + '"\n')
			if rdepend is not None:
				f.write('PDEPEND="' + str(pdepend) + '"\n')
			if required_use is not None:
				f.write('REQUIRED_USE="' + str(required_use) + '"\n')
			f.close()

	def _create_ebuild_manifests(self, ebuilds):
		for cpv in ebuilds:
			a = Atom("=" + cpv)
			ebuild_dir = os.path.join(self.portdir, a.cp)
			ebuild_path = os.path.join(ebuild_dir, a.cpv.split("/")[1] + ".ebuild")
			
			portage.util.noiselimit = -1
			tmpsettings = config(clone=self.settings)
			portdb = self.trees[self.root]["porttree"].dbapi
			portage.doebuild(ebuild_path, "digest", self.root, tmpsettings,
				tree="porttree", mydbapi=portdb)
			portage.util.noiselimit = 0
		
	def _create_installed(self, installed):
		for cpv in installed:
			a = Atom("=" + cpv)
			vdb_pkg_dir = os.path.join(self.vdbdir, a.cpv)
			try:
				os.makedirs(vdb_pkg_dir)
			except os.error:
				pass

			metadata = installed[cpv]
			eapi = metadata.get("EAPI", 0)
			slot = metadata.get("SLOT", 0)
			keywords = metadata.get("KEYWORDS", "~x86")
			iuse = metadata.get("IUSE", "")
			use = metadata.get("USE", "")
			depend = metadata.get("DEPEND", "")
			rdepend = metadata.get("RDEPEND", None)
			pdepend = metadata.get("PDEPEND", None)
			required_use = metadata.get("REQUIRED_USE", None)
			
			def write_key(key, value):
				f = open(os.path.join(vdb_pkg_dir, key), "w")
				f.write(str(value) + "\n")
				f.close()
			
			write_key("EAPI", eapi)
			write_key("SLOT", slot)
			write_key("KEYWORDS", keywords)
			write_key("IUSE", iuse)
			write_key("USE", use)
			write_key("DEPEND", depend)
			if rdepend is not None:
				write_key("RDEPEND", rdepend)
			if rdepend is not None:
				write_key("PDEPEND", pdepend)
			if required_use is not None:
				write_key("REQUIRED_USE", required_use)

	def _create_profile(self, ebuilds, installed, profile):
		#Create $PORTDIR/profiles/categories
		categories = set()
		for cpv in chain(ebuilds.keys(), installed.keys()):
			categories.add(catsplit(cpv)[0])
		
		profile_dir = os.path.join(self.portdir, "profiles")
		try:
			os.makedirs(profile_dir)
		except os.error:
			pass
		
		categories_file = os.path.join(profile_dir, "categories")
		
		f = open(categories_file, "w")
		for cat in categories:
			f.write(cat + "\n")
		f.close()
		
		#Create $PORTDIR/eclass (we fail to digest the ebuilds if it's not there)
		os.makedirs(os.path.join(self.portdir, "eclass"))
		
		if profile:
			#This is meant to allow the consumer to set up his own profile,
			#with package.mask and what not.
			raise NotImplentedError()

	def _load_config(self):
		env = {
			"ACCEPT_KEYWORDS": "x86",
			"PORTDIR": self.portdir,
			"ROOT": self.root,
			'PORTAGE_TMPDIR' : os.path.join(self.root, 'var/tmp')
		}

		settings = config(config_root=self.root, target_root=self.root, env=env)
		settings.lock()

		trees = {
			self.root: {
					"virtuals": settings.getvirtuals(),
					"vartree": vartree(self.root, categories=settings.categories, settings=settings),
					"porttree": portagetree(self.root, settings=settings),
					"bintree": binarytree(self.root, os.path.join(self.root, "usr/portage/packages"), settings=settings)
				}
			}

		for root, root_trees in trees.items():
			settings = root_trees["vartree"].settings
			settings._init_dirs()
			setconfig = SetConfig([], settings, root_trees)
			root_trees["root_config"] = RootConfig(settings, root_trees, setconfig)
			setconfig_fallback(root_trees["root_config"])
		
		return settings, trees

	def run(self, atoms, options={}, action=None):
		options = options.copy()
		options["--pretend"] = True
		options["--quiet"] = True
		options["--root"] = self.root
		options["--config-root"] = self.root
		options["--root-deps"] = "rdeps"
		# Add a fake _test_ option that can be used for
		# conditional test code.
		options["_test_"] = True

		portage.util.noiselimit = -2
		params = create_depgraph_params(options, action)
		success, depgraph, favorites = backtrack_depgraph(
			self.settings, self.trees, options, params, action, atoms, None)
		depgraph.display_problems()
		result = ResolverPlaygroundResult(atoms, success, depgraph, favorites)
		portage.util.noiselimit = 0

		return result

	def run_TestCase(self, test_case):
		if not isinstance(test_case, ResolverPlaygroundTestCase):
			raise TypeError("ResolverPlayground needs a ResolverPlaygroundTestCase")
		for atoms in test_case.requests:
			result = self.run(atoms, test_case.options, test_case.action)
			if not test_case.compare_with_result(result):
				return

	def cleanup(self):
		shutil.rmtree(self.root)

class ResolverPlaygroundTestCase(object):

	def __init__(self, request, **kwargs):
		self.checks = {
			"success": None,
			"mergelist": None,
			"use_changes": None,
			"unstable_keywords": None,
			"slot_collision_solutions": None,
			}
		
		self.all_permutations = kwargs.pop("all_permutations", False)
		self.ignore_mergelist_order = kwargs.pop("ignore_mergelist_order", False)

		if self.all_permutations:
			self.requests = list(permutations(request))
		else:
			self.requests = [request]

		self.options = kwargs.pop("options", {})
		self.action = kwargs.pop("action", None)
		self.test_success = True
		self.fail_msg = None
		
		for key, value in kwargs.items():
			if not key in self.checks:
				raise KeyError("Not an avaiable check: '%s'" % key)
			self.checks[key] = value
	
	def compare_with_result(self, result):
		fail_msgs = []
		for key, value in self.checks.items():
			got = getattr(result, key)
			expected = value
			if key == "mergelist" and self.ignore_mergelist_order and value is not None :
				got = set(got)
				expected = set(expected)
			elif key == "unstable_keywords" and expected is not None:
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
	def __init__(self, atoms, success, mydepgraph, favorites):
		self.atoms = atoms
		self.success = success
		self.depgraph = mydepgraph
		self.favorites = favorites
		self.mergelist = None
		self.use_changes = None
		self.unstable_keywords = None
		self.slot_collision_solutions = None

		if self.depgraph._dynamic_config._serialized_tasks_cache is not None:
			self.mergelist = []
			for x in self.depgraph._dynamic_config._serialized_tasks_cache:
				if isinstance(x, Blocker):
					self.mergelist.append(x.atom)
				else:
					self.mergelist.append(x.cpv)

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

		if self.depgraph._dynamic_config._slot_conflict_handler is not None:
			self.slot_collision_solutions  = []
			handler = self.depgraph._dynamic_config._slot_conflict_handler

			for solution in handler.solutions:
				s = {}
				for pkg in solution:
					changes = {}
					for flag, state in solution[pkg].items():
						if state == "enabled":
							changes[flag] = True
						else:
							changes[flag] = False
					s[pkg.cpv] = changes
				self.slot_collision_solutions.append(s)
