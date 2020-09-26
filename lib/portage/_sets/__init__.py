# Copyright 2007-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["SETPREFIX", "get_boolean", "SetConfigError",
	"SetConfig", "load_default_config"]

import io
import logging
import sys
import portage
from portage import os
from portage import load_mod
from portage import _unicode_decode
from portage import _unicode_encode
from portage import _encodings
from portage.const import USER_CONFIG_PATH, GLOBAL_CONFIG_PATH
from portage.const import VCS_DIRS
from portage.const import _ENABLE_SET_CONFIG
from portage.exception import PackageSetNotFound
from portage.localization import _
from portage.util import writemsg_level
from portage.util.configparser import (SafeConfigParser,
	NoOptionError, ParsingError, read_configs)

SETPREFIX = "@"

def get_boolean(options, name, default):
	if not name in options:
		return default
	if options[name].lower() in ("1", "yes", "on", "true"):
		return True
	if options[name].lower() in ("0", "no", "off", "false"):
		return False
	raise SetConfigError(_("invalid value '%(value)s' for option '%(option)s'") % {"value": options[name], "option": name})

class SetConfigError(Exception):
	pass

class SetConfig:
	def __init__(self, paths, settings, trees):
		self._parser = SafeConfigParser(
			defaults={
				"EPREFIX" : settings["EPREFIX"],
				"EROOT" : settings["EROOT"],
				"PORTAGE_CONFIGROOT" : settings["PORTAGE_CONFIGROOT"],
				"ROOT" : settings["ROOT"],
			})

		if _ENABLE_SET_CONFIG:
			read_configs(self._parser, paths)
		else:
			self._create_default_config()

		self.errors = []
		self.psets = {}
		self.trees = trees
		self.settings = settings
		self._parsed = False
		self.active = []

	def _create_default_config(self):
		"""
		Create a default hardcoded set configuration for a portage version
		that does not support set configuration files. This is only used
		in the current branch of portage if _ENABLE_SET_CONFIG is False.
		Even if it's not used in this branch, keep it here in order to
		minimize the diff between branches.

			[world]
			class = portage.sets.base.DummyPackageSet
			packages = @selected @system

			[selected]
			class = portage.sets.files.WorldSelectedSet

			[system]
			class = portage.sets.profiles.PackagesSystemSet

		"""
		parser = self._parser

		parser.remove_section("world")
		parser.add_section("world")
		parser.set("world", "class", "portage.sets.base.DummyPackageSet")
		parser.set("world", "packages", "@profile @selected @system")

		parser.remove_section("profile")
		parser.add_section("profile")
		parser.set("profile", "class", "portage.sets.ProfilePackageSet.ProfilePackageSet")

		parser.remove_section("selected")
		parser.add_section("selected")
		parser.set("selected", "class", "portage.sets.files.WorldSelectedSet")

		parser.remove_section("selected-packages")
		parser.add_section("selected-packages")
		parser.set("selected-packages", "class", "portage.sets.files.WorldSelectedPackagesSet")

		parser.remove_section("selected-sets")
		parser.add_section("selected-sets")
		parser.set("selected-sets", "class", "portage.sets.files.WorldSelectedSetsSet")

		parser.remove_section("system")
		parser.add_section("system")
		parser.set("system", "class", "portage.sets.profiles.PackagesSystemSet")

		parser.remove_section("security")
		parser.add_section("security")
		parser.set("security", "class", "portage.sets.security.NewAffectedSet")

		parser.remove_section("usersets")
		parser.add_section("usersets")
		parser.set("usersets", "class", "portage.sets.files.StaticFileSet")
		parser.set("usersets", "multiset", "true")
		parser.set("usersets", "directory", "%(PORTAGE_CONFIGROOT)setc/portage/sets")
		parser.set("usersets", "world-candidate", "true")

		parser.remove_section("live-rebuild")
		parser.add_section("live-rebuild")
		parser.set("live-rebuild", "class", "portage.sets.dbapi.VariableSet")
		parser.set("live-rebuild", "variable", "PROPERTIES")
		parser.set("live-rebuild", "includes", "live")

		parser.remove_section("deprecated-live-rebuild")
		parser.add_section("deprecated-live-rebuild")
		parser.set("deprecated-live-rebuild", "class", "portage.sets.dbapi.VariableSet")
		parser.set("deprecated-live-rebuild", "variable", "INHERITED")
		parser.set("deprecated-live-rebuild", "includes", " ".join(sorted(portage.const.LIVE_ECLASSES)))

		parser.remove_section("module-rebuild")
		parser.add_section("module-rebuild")
		parser.set("module-rebuild", "class", "portage.sets.dbapi.OwnerSet")
		parser.set("module-rebuild", "files", "/lib/modules")

		parser.remove_section("preserved-rebuild")
		parser.add_section("preserved-rebuild")
		parser.set("preserved-rebuild", "class", "portage.sets.libs.PreservedLibraryConsumerSet")

		parser.remove_section("x11-module-rebuild")
		parser.add_section("x11-module-rebuild")
		parser.set("x11-module-rebuild", "class", "portage.sets.dbapi.OwnerSet")
		parser.set("x11-module-rebuild", "files", "/usr/lib*/xorg/modules")
		parser.set("x11-module-rebuild", "exclude-files", "/usr/bin/Xorg")

	def update(self, setname, options):
		parser = self._parser
		self.errors = []
		if not setname in self.psets:
			options["name"] = setname
			options["world-candidate"] = "False"

			# for the unlikely case that there is already a section with the requested setname
			import random
			while setname in parser.sections():
				setname = "%08d" % random.randint(0, 10**10)

			parser.add_section(setname)
			for k, v in options.items():
				parser.set(setname, k, v)
		else:
			section = self.psets[setname].creator
			if parser.has_option(section, "multiset") and \
				parser.getboolean(section, "multiset"):
				self.errors.append(_("Invalid request to reconfigure set '%(set)s' generated "
					"by multiset section '%(section)s'") % {"set": setname, "section": section})
				return
			for k, v in options.items():
				parser.set(section, k, v)
		self._parse(update=True)

	def _parse(self, update=False):
		if self._parsed and not update:
			return
		parser = self._parser
		for sname in parser.sections():
			# find classname for current section, default to file based sets
			if not parser.has_option(sname, "class"):
				classname = "portage._sets.files.StaticFileSet"
			else:
				classname = parser.get(sname, "class")

			if classname.startswith('portage.sets.'):
				# The module has been made private, but we still support
				# the previous namespace for sets.conf entries.
				classname = classname.replace('sets', '_sets', 1)

			# try to import the specified class
			try:
				setclass = load_mod(classname)
			except (ImportError, AttributeError):
				try:
					setclass = load_mod("portage._sets." + classname)
				except (ImportError, AttributeError):
					self.errors.append(_("Could not import '%(class)s' for section "
						"'%(section)s'") % {"class": classname, "section": sname})
					continue
			# prepare option dict for the current section
			optdict = {}
			for oname in parser.options(sname):
				optdict[oname] = parser.get(sname, oname)

			# create single or multiple instances of the given class depending on configuration
			if parser.has_option(sname, "multiset") and \
				parser.getboolean(sname, "multiset"):
				if hasattr(setclass, "multiBuilder"):
					newsets = {}
					try:
						newsets = setclass.multiBuilder(optdict, self.settings, self.trees)
					except SetConfigError as e:
						self.errors.append(_("Configuration error in section '%s': %s") % (sname, str(e)))
						continue
					for x in newsets:
						if x in self.psets and not update:
							self.errors.append(_("Redefinition of set '%s' (sections: '%s', '%s')") % (x, self.psets[x].creator, sname))
						newsets[x].creator = sname
						if parser.has_option(sname, "world-candidate") and \
							parser.getboolean(sname, "world-candidate"):
							newsets[x].world_candidate = True
					self.psets.update(newsets)
				else:
					self.errors.append(_("Section '%(section)s' is configured as multiset, but '%(class)s' "
						"doesn't support that configuration") % {"section": sname, "class": classname})
					continue
			else:
				try:
					setname = parser.get(sname, "name")
				except NoOptionError:
					setname = sname
				if setname in self.psets and not update:
					self.errors.append(_("Redefinition of set '%s' (sections: '%s', '%s')") % (setname, self.psets[setname].creator, sname))
				if hasattr(setclass, "singleBuilder"):
					try:
						self.psets[setname] = setclass.singleBuilder(optdict, self.settings, self.trees)
						self.psets[setname].creator = sname
						if parser.has_option(sname, "world-candidate") and \
							parser.getboolean(sname, "world-candidate"):
							self.psets[setname].world_candidate = True
					except SetConfigError as e:
						self.errors.append(_("Configuration error in section '%s': %s") % (sname, str(e)))
						continue
				else:
					self.errors.append(_("'%(class)s' does not support individual set creation, section '%(section)s' "
						"must be configured as multiset") % {"class": classname, "section": sname})
					continue
		self._parsed = True

	def getSets(self):
		self._parse()
		return self.psets.copy()

	def getSetAtoms(self, setname, ignorelist=None):
		"""
		This raises PackageSetNotFound if the give setname does not exist.
		"""
		self._parse()
		try:
			myset = self.psets[setname]
		except KeyError:
			raise PackageSetNotFound(setname)
		myatoms = myset.getAtoms()

		if ignorelist is None:
			ignorelist = set()

		ignorelist.add(setname)
		for n in myset.getNonAtoms():
			if n.startswith(SETPREFIX):
				s = n[len(SETPREFIX):]
				if s in self.psets:
					if s not in ignorelist:
						myatoms.update(self.getSetAtoms(s,
							ignorelist=ignorelist))
				else:
					raise PackageSetNotFound(s)

		return myatoms

def load_default_config(settings, trees):

	if not _ENABLE_SET_CONFIG:
		return SetConfig(None, settings, trees)

	global_config_path = GLOBAL_CONFIG_PATH
	if portage.const.EPREFIX:
		global_config_path = os.path.join(portage.const.EPREFIX,
			GLOBAL_CONFIG_PATH.lstrip(os.sep))
	vcs_dirs = [_unicode_encode(x, encoding=_encodings['fs']) for x in VCS_DIRS]
	def _getfiles():
		for path, dirs, files in os.walk(os.path.join(global_config_path, "sets")):
			for d in dirs:
				if d in vcs_dirs or d.startswith(b".") or d.endswith(b"~"):
					dirs.remove(d)
			for f in files:
				if not f.startswith(b".") and not f.endswith(b"~"):
					yield os.path.join(path, f)

		dbapi = trees["porttree"].dbapi
		for repo in dbapi.getRepositories():
			path = dbapi.getRepositoryPath(repo)
			yield os.path.join(path, "sets.conf")

		yield os.path.join(settings["PORTAGE_CONFIGROOT"],
			USER_CONFIG_PATH, "sets.conf")

	return SetConfig(_getfiles(), settings, trees)
