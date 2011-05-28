#!/usr/bin/python
#
# Copyright 1998-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Portage API settings class for consumer apps."""

import os

from _emerge.actions import load_emerge_config
import portage
from portage import const


class PortageSettings:
	"""This class hold an instance of the portage settings as
	well as some other commonly used data used in/from the  api.
	"""

	def __init__(self, config_root=None):
		# declare some globals
		self.portdir = None
		self.portdir_overlay = None
		self.portdb = None
		self.vardb = None
		self.trees = None
		self.root_config = None
		self.bindb = None
		self.configured_roots = None
		self.arch = None
		self.mtimedb = None
		self.ACCEPT_KEYWORDS = None
		self.user_config_dir = None
		self._world = None
		self.SystemUseFlags = None
		self.virtuals =  None
		self.keys =  None
		self.UseFlagDict = None
		self.settings = None
		if config_root is None:
			self.reset()
		else:
			self.config_root = config_root



	def reset_use_flags(self):
		"""Resets the SystemUseFlags to any new
		changes to their setting.
		"""
		#print("SETTINGS: Settings.reset_use_flags();")
		self.SystemUseFlags = self.settings["USE"].split()
		#print("SETTINGS: Settings.reset_use_flags(); SystemUseFlags = " +
			#str(self.SystemUseFlags))


	def reset(self):
		"""Reset remaining run once variables after a sync or other mods
		"""
		#print("SETTINGS: reset_globals();")
		self.settings, self.trees, self.mtimedb = load_emerge_config()
		self._load_dbapis()
		self.root_config = self.trees[self.settings['ROOT']]['root_config']
		self.portdir = self.settings.environ()['PORTDIR']
		self.config_root = self.settings['PORTAGE_CONFIGROOT']
		# is PORTDIR_OVERLAY always defined?
		self.portdir_overlay = self.settings.environ()['PORTDIR_OVERLAY']
		self.ACCEPT_KEYWORDS = self.settings["ACCEPT_KEYWORDS"]
		self.arch = self.settings['ARCH']
		self.user_config_dir = const.USER_CONFIG_PATH
		self.reload_world()
		self.reset_use_flags()
		self.virtuals = self.settings.getvirtuals()
		# lower case is nicer
		self.keys = [key.lower() for key in portage.auxdbkeys]
		return


	def _load_dbapis(self):
		"""handles loading all the trees dbapi's"""
		self.portdb, self.vardb, self.bindb = {}, {}, {}
		self.configured_roots = sorted(self.trees)
		for root in self.configured_roots:
			self.portdb[root] = self.trees[root]["porttree"].dbapi
			self.vardb[root] = self.trees[root]["vartree"].dbapi
			self.bindb[root] = self.trees[root]["bintree"].dbapi


	def reload_config(self):
		"""Reload the whole config from scratch"""
		self.settings, self.trees, self.mtimedb = load_emerge_config(self.trees)
		self._load_dbapis()

	def reload_world(self):
		"""Reloads the world file into memory for quick access
		@return boolean
		"""
		#print("SETTINGS: reset_world();")
		world = []
		try:
			_file = open(os.path.join(portage.root, portage.WORLD_FILE), "r")
			world = _file.read().split()
			_file.close()
		except:
			print("SETTINGS: get_world(); Failure to locate file: '%s'"
				%portage.WORLD_FILE)
			return False
		self._world = world
		return True


	def get_world(self):
		"""Returns a copy of world's pkg list
		@return list of world pkg strings
		"""
		return self._world[:]


	def get_archlist(self):
		"""Returns a list of the architectures accepted by portage as valid keywords.
		@return: list of arch strings
		"""
		return self.settings["PORTAGE_ARCHLIST"].split()


	def get_virtuals(self):
		"""returns the virtual pkgs
		@rtype dict
		@return virtual pkgs dictionary
		"""
		return self.settings.virtuals


default_settings = PortageSettings()


def reload_portage(settings=None):
	"""Convienence function to re-import portage after a portage update.
	Caution, it may not always work correctly due to python caching if
	program files are added/deleted between versions. In those cases the
	consumer app may need to be closed and restarted."""
	#print('SETTINGS: reloading portage')
	#print("SETTINGS: old portage version = " + portage.VERSION)
	try:
		reload(portage)
	except ImportError:
		return False
	#print("SETTINGS: new portage version = " + portage.VERSION)
	if settings is None:
		default_settings.reset()
	else:
		settings.reset()
	return True
