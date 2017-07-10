
'''
moudules/scan/module.py
Module loading and run list generator
'''

import logging
import os
import yaml

from portage.module import InvalidModuleName, Modules
from portage.util import stack_lists

MODULES_PATH = os.path.dirname(__file__)
# initial development debug info
logging.debug("module path: %s", MODULES_PATH)


class ModuleConfig(object):
	'''Holds the scan modules configuration information and
	creates the ordered list of modulles to run'''

	def __init__(self, configpaths):
		'''Module init

		@param configpaths: ordered list of filepaths to load
		'''
		self.configpaths = configpaths

		self.controller = Modules(path=MODULES_PATH, namepath="repoman.modules.scan")
		logging.debug("module_names: %s", self.controller.module_names)

		self._configs = None
		self.enabled = []
		self.pkgs_loop = []
		self.ebuilds_loop = []
		self.final_loop = []
		self.modules_forced = ['ebuild', 'mtime']
		self.load_configs()
		for loop in ['pkgs', 'ebuilds', 'final']:
			logging.debug("ModuleConfig; Processing loop %s", loop)
			setattr(self, '%s_loop' % loop, self._determine_list(loop))


	def load_configs(self, configpaths=None):
		'''load the config files in order'''
		if configpaths:
			self.configpaths = configpaths
		elif not self.configpaths:
			logging.error("ModuleConfig; Error: No repository.yml files defined")
		configs = []
		for path in self.configpaths:
			logging.debug("ModuleConfig; Processing: %s", path)
			if os.path.exists(path):
				try:
					with open(path, 'r') as inputfile:
						configs.append(yaml.safe_load(inputfile.read()))
				except IOError as error:
					logging,error("Failed to load file: %s", inputfile)
					logging.exception(error)
			logging.debug("ModuleConfig; completed : %s", path)
		logging.debug("ModuleConfig; new _configs: %s", configs)
		self._configs = configs

	def _determine_list(self, loop):
		'''Determine the ordered list from the config data and
		the moule_runsIn value in the module_spec

		@returns: list of modules
		'''
		lists = [c['scan_modules'].split() for c in self._configs]
		stacked = self.modules_forced + stack_lists(lists)
		mlist = []
		try:
			for mod in stacked:
				logging.debug("ModuleConfig; checking loop %s, module: %s, in: %s",
					loop, mod, self.controller.get_spec(mod, 'module_runsIn'))
				if loop in self.controller.get_spec(mod, 'module_runsIn'):
					mlist.append(mod)
		except InvalidModuleName:
			logging.error("ModuleConfig; unkown module: %s, skipping", mod)

		logging.debug("ModuleConfig; mlist: %s", mlist)
		return mlist
