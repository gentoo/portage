# -*- coding:utf-8 -*-
# repoman: Checks
# Copyright 2007-2017 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""This module contains functions used in Repoman to ascertain the quality
and correctness of an ebuild."""

from __future__ import unicode_literals

import collections
import logging
import os
import yaml
from copy import deepcopy

from portage.util import stack_lists
from repoman.config import load_config


def merge(dict1, dict2):
    ''' Return a new dictionary by merging two dictionaries recursively. '''

    result = deepcopy(dict1)

    for key, value in dict2.items():
        if isinstance(value, collections.Mapping):
            result[key] = merge(result.get(key, {}), value)
        else:
            result[key] = deepcopy(dict2[key])

    return result


class LineChecksConfig(object):
	'''Holds our LineChecks configuration data and operation functions'''

	def __init__(self, repo_settings):
		'''Class init

		@param repo_settings: RepoSettings instance
		@param configpaths: ordered list of filepaths to load
		'''
		self.repo_settings = repo_settings
		self.infopaths = [os.path.join(path, 'linechecks.yaml') for path in self.repo_settings.masters_list]
		logging.debug("LineChecksConfig; configpaths: %s", self.infopaths)
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
		self.load_checks_info()


	def load_checks_info(self, infopaths=None):
		'''load the config files in order

		@param configpaths: ordered list of filepaths to load
		'''
		if infopaths:
			self.infopaths = infopaths
		elif not self.infopaths:
			logging.error("LineChecksConfig; Error: No linechecks.yaml files defined")
		configs = load_config(self.infopaths, 'yaml')
		if configs == {}:
			logging.error("LineChecksConfig: Failed to load a valid 'linechecks.yaml' file at paths: %s", self.infopaths)
			return False
		logging.debug("LineChecksConfig: linechecks.yaml configs: %s", configs)
		self.info_config = configs

		self.errors = self.info_config['errors']
		self.usex_supported_eapis = self.info_config['usex_supported_eapis']
		self.in_iuse_supported_eapis = self.info_config['in_iuse_supported_eapis']
		self.eclass_info_experimental_inherit = self.info_config['eclass_info_experimental_inherit']
		self.get_libdir_supported_eapis = self.in_iuse_supported_eapis
		self.eclass_eapi_functions = {
			"usex": lambda eapi: eapi not in self.usex_supported_eapis,
			"in_iuse": lambda eapi: eapi not in self.in_iuse_supported_eapis,
			"get_libdir": lambda eapi: eapi not in self.get_libdir_supported_eapis,
		}

		# eclasses that export ${ECLASS}_src_(compile|configure|install)
		self.eclass_export_functions = self.info_config['eclass_export_functions']

		self.eclass_info_experimental_inherit = self.info_config['eclass_info_experimental_inherit']
		# These are "eclasses are the whole ebuild" type thing.
		self.eclass_info_experimental_inherit['eutils']['exempt_eclasses'] = self.eclass_export_functions
		self.eclass_info_experimental_inherit['multilib']['exempt_eclasses'] = self.eclass_export_functions + [
						'autotools', 'libtool', 'multilib-minimal']
