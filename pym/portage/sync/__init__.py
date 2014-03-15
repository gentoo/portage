# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import os

from portage.emaint.module import Modules
from portage.sync.controller import SyncManager

sync_manager = None

path = os.path.join(os.path.dirname(__file__), "modules")
# initial development debug info
print("module path:", path)

module_controller = Modules(path=path, namepath="portage.sync.modules")

# initial development debug info
print(module_controller.module_names)
module_names = module_controller.module_names[:]


def get_syncer(settings=None, logger=None):
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



