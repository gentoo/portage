# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os

from portage.emaint.module import Modules
from portage.sync.controller import SyncManager
from portage.sync.config_checks import check_type

sync_manager = None

path = os.path.join(os.path.dirname(__file__), "modules")
# initial development debug info
print("module path:", path)

module_controller = Modules(path=path, namepath="portage.sync.modules")

# initial development debug info
print(module_controller.module_names)
module_names = module_controller.module_names[:]


def get_syncer(settings=None, logger=None):
	'''Initializes and returns the SyncManager instance
	to be used for sync operations

	@param settings:  emerge.settings instance
	@param logger: emerge logger instance
	@returns SyncManager instance
	'''
	global sync_manager
	if sync_manager and not settings and not logger:
		return sync_manager
	if settings is None:
		from _emerge.actions import load_emerge_config
		emerge_config = load_emerge_config()
		settings = emerge_config.target_config.settings
	if logger is None:
		from _emerge.emergelog import emergelog as logger
	sync_manager = SyncManager(settings, logger)
	return sync_manager


def validate_config(repo, logger):
	'''Validate the repos.conf settings for the repo'''
	if not check_type(repo, logger, module_names):
		return False

	#print(repo)
	if repo.sync_type:
		validated = module_controller.modules[repo.sync_type]['validate_config']
		return validated(repo, logger).repo_checks()
	return True
