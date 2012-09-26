# Copyright 2007-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

__all__ = ["SETPREFIX", "get_boolean", "SetConfigError",
	"SetConfig", "load_default_config"]

import io
import logging
import sys
try:
	from configparser import NoOptionError, ParsingError
	if sys.hexversion >= 0x3020000:
		from configparser import ConfigParser as SafeConfigParser
	else:
		from configparser import SafeConfigParser
except ImportError:
	from ConfigParser import SafeConfigParser, NoOptionError, ParsingError
from portage import os
from portage import load_mod
from portage import _unicode_decode
from portage import _unicode_encode
from portage import _encodings
from portage.const import USER_CONFIG_PATH, GLOBAL_CONFIG_PATH
from portage.const import _ENABLE_SET_CONFIG
from portage.exception import PackageSetNotFound
from portage.localization import _
from portage.util import writemsg_level

SETPREFIX = "@"

def get_boolean(options, name, default):
	if not name in options:
		return default
	elif options[name].lower() in ("1", "yes", "on", "true"):
		return True
	elif options[name].lower() in ("0", "no", "off", "false"):
		return False
	else:
		raise SetConfigError(_("invalid value '%(value)s' for option '%(option)s'") % {"value": options[name], "option": name})

class SetConfigError(Exception):
	pass

class SetConfig(object):
	def __init__(self, paths, settings, trees):
		self._parser = SafeConfigParser(
			defaults={
				"EPREFIX" : settings["EPREFIX"],
				"EROOT" : settings["EROOT"],
				"PORTAGE_CONFIGROOT" : settings["PORTAGE_CONFIGROOT"],
				"ROOT" : settings["ROOT"],
			})

		if _ENABLE_SET_CONFIG:
			# use read_file/readfp in order to control decoding of unicode
			try:
				# Python >=3.2
				read_file = self._parser.read_file
			except AttributeError:
				read_file = self._parser.readfp

			for p in paths:
				f = None
				try:
					f = io.open(_unicode_encode(p,
						encoding=_encodings['fs'], errors='strict'),
						mode='r', encoding=_encodings['repo.content'],
						errors='replace')
				except EnvironmentError:
					pass
				else:
					try:
						read_file(f)
					except ParsingError as e:
						writemsg_level(_unicode_decode(
							_("!!! Error while reading sets config file: %s\n")
							) % e, level=logging.ERROR, noiselevel=-1)
				finally:
					if f is not None:
						f.close()
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
		parser.set("world", "packages", "@selected @system")

		parser.remove_section("selected")
		parser.add_section("selected")
		parser.set("selected", "class", "portage.sets.files.WorldSelectedSet")

		parser.remove_section("system")
		parser.add_section("system")
		parser.set("system", "class", "portage.sets.profiles.PackagesSystemSet")

		parser.remove_section("usersets")
		parser.add_section("usersets")
		parser.set("usersets", "class", "portage.sets.files.StaticFileSet")
		parser.set("usersets", "multiset", "true")
		parser.set("usersets", "directory", "%(PORTAGE_CONFIGROOT)setc/portage/sets")
		parser.set("usersets", "world-candidate", "true")

		parser.remove_section("live-rebuild")
		parser.add_section("live-rebuild")
		parser.set("live-rebuild", "class", "portage.sets.dbapi.VariableSet")
		parser.set("live-rebuild", "variable", "INHERITED")
		parser.set("live-rebuild", "includes", "bzr cvs darcs git git-2 mercurial subversion tla")

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
		parser.set("x11-module-rebuild", "files", "/usr/lib/xorg/modules")
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
	if settings['EPREFIX']:
		global_config_path = os.path.join(settings['EPREFIX'],
			GLOBAL_CONFIG_PATH.lstrip(os.sep))
	def _getfiles():
		for path, dirs, files in os.walk(os.path.join(global_config_path, "sets")):
			for f in files:
				if not f.startswith(b'.'):
					yield os.path.join(path, f)

		dbapi = trees["porttree"].dbapi
		for repo in dbapi.getRepositories():
			path = dbapi.getRepositoryPath(repo)
			yield os.path.join(path, "sets.conf")

		yield os.path.join(settings["PORTAGE_CONFIGROOT"],
			USER_CONFIG_PATH, "sets.conf")

	return SetConfig(_getfiles(), settings, trees)
