# Copyright 2014-2019 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import os

from collections import OrderedDict
from pathlib import Path

from portage.module import Modules
from portage.sync.controller import SyncManager
from portage.sync.config_checks import check_type

_SUBMODULE_PATH_MAP = OrderedDict([
	('glsa', (Path('metadata/glsa'),)),
	('news', (Path('metadata/news'),)),
	('profiles', (Path('metadata/layout.conf'), Path('profiles'))),
])

path = Path(__file__).parent / "modules"
# initial development debug info
#print("module path:", path)

module_controller = Modules(path=path, namepath="portage.sync.modules")

# initial development debug info
#print(module_controller.module_names)
module_names = module_controller.module_names[:]


def module_specific_options(repo):
	'''Get the authorized module specific options set for
	the repos.conf settings for the repo'''
	global module_controller

	if repo.sync_type:
		try:
			return frozenset(
				module_controller.modules[repo.sync_type]['module_specific_options'])
		except KeyError:
			pass
	return frozenset()


def validate_config(repo, logger):
	'''Validate the repos.conf settings for the repo'''
	global module_names, module_controller
	if not check_type(repo, logger, module_names):
		return False

	#print(repo)
	if repo.sync_type:
		validated = module_controller.modules[repo.sync_type]['validate_config']
		return validated(repo, logger).repo_checks()
	return True
