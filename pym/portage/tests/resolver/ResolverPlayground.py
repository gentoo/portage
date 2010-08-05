# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from itertools import chain
import shutil
import tempfile
import portage
from portage import os
from portage.dbapi.vartree import vartree
from portage.dbapi.porttree import portagetree
from portage.dbapi.bintree import binarytree
from portage.dep import Atom
from portage.package.ebuild.config import config
from portage.sets import load_default_config
from portage.versions import catsplit

from _emerge.create_depgraph_params import create_depgraph_params
from _emerge.depgraph import backtrack_depgraph
from _emerge.RootConfig import RootConfig

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
		env = { "PORTDIR": self.portdir, "ROOT": self.root, "ACCEPT_KEYWORDS": "x86"}
		settings = config(config_root=self.root, target_root=self.root, local_config=False, env=env)
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
			setconfig = load_default_config(settings, root_trees)
			root_trees["root_config"] = RootConfig(settings, root_trees, setconfig)
		
		return settings, trees

	def run(self, myfiles, myopts={}, myaction=None):
		myopts["--pretend"] = True
		myopts["--quiet"] = True
		myopts["--root"] = self.root
		myopts["--config-root"] = self.root
		myopts["--root-deps"] = "rdeps"
		# Add a fake _test_ option that can be used for
		# conditional test code.
		myopts["_test_"] = True
		
		portage.util.noiselimit = -2
		myparams = create_depgraph_params(myopts, myaction)
		success, mydepgraph, favorites = backtrack_depgraph(
			self.settings, self.trees, myopts, myparams, myaction, myfiles, None)
		portage.util.noiselimit = 0

		if success:
			mergelist = [x.cpv for x in mydepgraph._dynamic_config._serialized_tasks_cache]
			return True, mergelist
		else:
			#TODO: Use mydepgraph.display_problems() to return a useful error message
			return False, None

	def cleanup(self):
		shutil.rmtree(self.root)
