#!/usr/bin/python
#
# Copyright 1998-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Portage API settings class for consumer apps.  """


from _emerge.actions import load_emerge_config
import portage
from portage import const


class PortageSettings:
	"""This class hold an instance of the portage settings as
	well as some other commonly used data used in/from the  api.
	"""
	
	def __init__(self):
		# declare some globals
		self.portdir = None
		self.portdir_overlay = None
		self.ACCEPT_KEYWORDS = None 
		self.user_config_dir = None
		self._world = None
		self.SystemUseFlags = None
		self.virtuals =  None
		self.keys =  None
		self.UseFlagDict = None
		self.reset()


	def reset_use_flags(self):
		"""resets the SystemUseFlags to any new setting"""
		#debug.dprint("SETTINGS: Settings.reset_use_flags();")
		self.SystemUseFlags = self.settings["USE"].split()
		#debug.dprint("SETTINGS: Settings.reset_use_flags(); SystemUseFlags = " + str(SystemUseFlags))


	def reset(self):
		"""Reset remaining run once variables after a sync or other mods"""
		#debug.dprint("SETTINGS: reset_globals();")
		self.settings, self.trees, self.mtimedb = load_emerge_config()
		self.portdb = self.trees[self.settings["ROOT"]]["porttree"].dbapi
		self.vardb = self.trees[self.settings["ROOT"]]["vartree"].dbapi
		self.bindb = self.trees[self.settings["ROOT"]]["bintree"].dbapi
		self.portdir = self.settings.environ()['PORTDIR']
		self.config_root = self.settings['PORTAGE_CONFIGROOT']
		# is PORTDIR_OVERLAY always defined?
		self.portdir_overlay = self.settings.environ()['PORTDIR_OVERLAY']
		self.ACCEPT_KEYWORDS = self.settings["ACCEPT_KEYWORDS"]
		self.arch = self.settings['ARCH']
		self.user_config_dir = const.USER_CONFIG_PATH
		self.reload_world()
		self.reset_use_flags()
		self.virtuals = self.settings.virtuals
		# lower case is nicer
		self.keys = [key.lower() for key in portage.auxdbkeys]
		return


	def reload_config(self):
		"""Reload the whole config from scratch"""
		self.settings, self.trees, self.mtimedb = load_emerge_config(self.trees)
		self.portdb = self.trees[self.settings["ROOT"]]["porttree"].dbapi

	def reload_world(self):
		"""Reloads the world file into memory for quick access"""
		#debug.dprint("SETTINGS: reset_world();")
		world = []
		try:
			file = open(os.path.join(portage.root, portage.WORLD_FILE), "r")
			world = file.read().split()
			file.close()
		except:
			pass
			#debug.dprint("SETTINGS: get_world(); Failure to locate file: '%s'" %portage.WORLD_FILE)
		self._world = world


	def get_world(self):
		"""Returns a copy of world's pkg list"""
		return self._world[:]


	def get_archlist(self):
		"""Returns a list of the architectures accepted by portage as valid keywords"""
		return self.settings["PORTAGE_ARCHLIST"].split()


	def get_virtuals(self):
		"""returns the virtual pkgs"""
		return self.settings.virtuals


settings = PortageSettings()


def reload_portage():
	"""Convienence function to re-import portage after a portage update.
	Caution, it may not always work correctly due to python caching if
	program files are added/deleted between versions. In those cases the
	consumer app may need to be closed and restarted."""
	#debug.dprint('SETTINGS: reloading portage')
	#debug.dprint("SETTINGS: old portage version = " + portage.VERSION)
	try:
		reload(portage)
	except ImportError:
		return False
	#debug.dprint("SETTINGS: new portage version = " + portage.VERSION)
	settings.reset()
	return True
