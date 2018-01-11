# Copyright 2018-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Mercurial plug-in module for portage.
Performs a hg pull on repositories."""
__doc__ = doc[:]

from portage.localization import _
from portage.sync.config_checks import CheckSyncConfig
from portage.util import writemsg_level

module_spec = {
	"name": "mercurial",
	"description": doc,
	"provides": {
		"mercurial-module": {
			"name": "mercurial",
			"sourcefile": "mercurial",
			"class": "MercurialSync",
			"description": doc,
			"functions": ["sync", "new", "exists", "retrieve_head"],
			"func_desc": {
				"sync": "Performs a hg pull on the repository",
				"new": "Creates the new repository at the specified location",
				"exists": "Returns a boolean of whether the specified dir "
				+ "exists and is a valid Mercurial repository",
				"retrieve_head": "Returns the head commit hash",
			},
			"validate_config": CheckSyncConfig,
			"module_specific_options": (
				"sync-mercurial-clone-env",
				"sync-mercurial-clone-extra-opts",
				"sync-mercurial-env",
				"sync-mercurial-pull-env",
				"sync-mercurial-pull-extra-opts",
			),
		}
	},
}
