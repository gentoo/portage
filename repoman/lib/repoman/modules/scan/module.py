
'''
moudules/scan/module.py
Module loading and run list generator
'''

import logging
import os
import yaml

import portage
from portage.module import InvalidModuleName, Modules
from portage.util import stack_lists
from repoman import _not_installed
from repoman.config import ConfigError

MODULES_PATH = os.path.dirname(__file__)
# initial development debug info
logging.debug("module path: %s", MODULES_PATH)


class ModuleConfig:
	'''Holds the scan modules configuration information and
	creates the ordered list of modulles to run'''

	def __init__(self, configpaths, valid_versions=None, repository_modules=False):
		'''Module init

		@param configpaths: ordered list of filepaths to load
		'''
		if repository_modules:
			self.configpaths = [os.path.join(path, 'repository.yaml') for path in configpaths]
		elif _not_installed:
			self.configpaths = [os.path.realpath(os.path.join(os.path.dirname(
				os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
				os.path.dirname(__file__)))))), 'repoman/cnf/repository/repository.yaml'))]
		else:
			self.configpaths = [os.path.join(portage.const.EPREFIX or '/',
				'usr/share/repoman/repository/repository.yaml')]
		logging.debug("ModuleConfig; configpaths: %s", self.configpaths)

		self.controller = Modules(path=MODULES_PATH, namepath="repoman.modules.scan")
		logging.debug("ModuleConfig; module_names: %s", self.controller.module_names)

		self._configs = None
		self.enabled = []
		self.pkgs_loop = []
		self.ebuilds_loop = []
		self.final_loop = []
		self.modules_forced = ['ebuild', 'mtime']
		self.load_configs(valid_versions=valid_versions)
		for loop in ['pkgs', 'ebuilds', 'final']:
			logging.debug("ModuleConfig; Processing loop %s", loop)
			setattr(self, '%s_loop' % loop, self._determine_list(loop))
		self.linechecks = stack_lists(c['linechecks_modules'].split() for c in self._configs)

	def load_configs(self, configpaths=None, valid_versions=None):
		'''load the config files in order

		@param configpaths: ordered list of filepaths to load
		'''
		if configpaths:
			self.configpaths = configpaths
		elif not self.configpaths:
			logging.error("ModuleConfig; Error: No repository.yaml files defined")
		configs = []
		for path in self.configpaths:
			logging.debug("ModuleConfig; Processing: %s", path)
			if os.path.exists(path):
				try:
					with open(path, 'r') as inputfile:
						configs.append(yaml.safe_load(inputfile))
				except IOError as error:
					logging,error("Failed to load file: %s", inputfile)
					logging.exception(error)
				else:
					if configs[-1]['version'] not in valid_versions:
						raise ConfigError("Invalid file version: %s in: %s\nPlease upgrade repoman" % (configs['version'], path))
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
			logging.error("ModuleConfig; unknown module: %s, skipping", mod)

		logging.debug("ModuleConfig; mlist: %s", mlist)
		return mlist
