# -*- coding:utf-8 -*-
# repoman: Checks
# Copyright 2007-2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""This module contains functions used in Repoman to ascertain the quality
and correctness of an ebuild."""

import collections
import logging
import os
from copy import deepcopy

from repoman._portage import portage
from repoman.config import load_config
from repoman import _not_installed

# Avoid a circular import issue in py2.7
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.util:stack_lists',
)


def merge(dict1, dict2):
    ''' Return a new dictionary by merging two dictionaries recursively. '''

    result = deepcopy(dict1)

    for key, value in dict2.items():
        if isinstance(value, collections.Mapping):
            result[key] = merge(result.get(key, {}), value)
        else:
            result[key] = deepcopy(dict2[key])

    return result


class LineChecksConfig:
	'''Holds our LineChecks configuration data and operation functions'''

	def __init__(self, repo_settings):
		'''Class init

		@param repo_settings: RepoSettings instance
		@param configpaths: ordered list of filepaths to load
		'''
		self.repo_settings = repo_settings
		self.infopaths = None
		self.info_config = None
		self._config = None
		self.usex_supported_eapis = None
		self.in_iuse_supported_eapis = None
		self.get_libdir_supported_eapis = None
		self.eclass_eapi_functions = {}
		self.eclass_export_functions = None
		self.eclass_info = {}
		self.eclass_info_experimental_inherit = {}
		self.errors = {}
		self.set_infopaths()
		self.load_checks_info()

	def set_infopaths(self):
		if _not_installed:
			cnfdir = os.path.realpath(os.path.join(os.path.dirname(
				os.path.dirname(os.path.dirname(os.path.dirname(
				os.path.dirname(__file__))))), 'cnf/linechecks'))
		else:
			cnfdir = os.path.join(portage.const.EPREFIX or '/', 'usr/share/repoman/linechecks')
		repomanpaths = [os.path.join(cnfdir, _file_) for _file_ in os.listdir(cnfdir)]
		logging.debug("LineChecksConfig; repomanpaths: %s", repomanpaths)
		repopaths = [os.path.join(path, 'linechecks.yaml') for path in self.repo_settings.masters_list]
		self.infopaths = repomanpaths + repopaths
		logging.debug("LineChecksConfig; configpaths: %s", self.infopaths)

	def load_checks_info(self, infopaths=None):
		'''load the config files in order

		@param infopaths: ordered list of filepaths to load
		'''
		if infopaths:
			self.infopaths = infopaths
		elif not self.infopaths:
			logging.error("LineChecksConfig; Error: No linechecks.yaml files defined")

		configs = load_config(self.infopaths, 'yaml', self.repo_settings.repoman_settings.valid_versions)
		if configs == {}:
			logging.error("LineChecksConfig: Failed to load a valid 'linechecks.yaml' file at paths: %s", self.infopaths)
			return False
		logging.debug("LineChecksConfig: linechecks.yaml configs: %s", configs)
		self.info_config = configs

		self.errors = self.info_config['errors']
		self.usex_supported_eapis = self.info_config.get('usex_supported_eapis', [])
		self.in_iuse_supported_eapis = self.info_config.get('in_iuse_supported_eapis', [])
		self.eclass_info_experimental_inherit = self.info_config.get('eclass_info_experimental_inherit', [])
		self.get_libdir_supported_eapis = self.in_iuse_supported_eapis
		self.eclass_eapi_functions = {
			"usex": lambda eapi: eapi not in self.usex_supported_eapis,
			"in_iuse": lambda eapi: eapi not in self.in_iuse_supported_eapis,
			"get_libdir": lambda eapi: eapi not in self.get_libdir_supported_eapis,
		}

		# eclasses that export ${ECLASS}_src_(compile|configure|install)
		self.eclass_export_functions = self.info_config.get('eclass_export_functions', [])

		self.eclass_info_experimental_inherit = self.info_config.get('eclass_info_experimental_inherit', {})
		# These are "eclasses are the whole ebuild" type thing.
		try:
			self.eclass_info_experimental_inherit['eutils']['exempt_eclasses'] = self.eclass_export_functions
		except KeyError:
			pass
		try:
			self.eclass_info_experimental_inherit['multilib']['exempt_eclasses'] = self.eclass_export_functions + [
						'autotools', 'libtool', 'multilib-minimal']
		except KeyError:
			pass
