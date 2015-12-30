# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """SVN plug-in module for portage.
Performs a svn up on repositories."""
__doc__ = doc[:]

from portage.localization import _
from portage.sync.config_checks import CheckSyncConfig
from portage.util import writemsg_level


module_spec = {
	'name': 'svn',
	'description': doc,
	'provides':{
		'svn-module': {
			'name': "svn",
			'sourcefile': "svn",
			'class': "SVNSync",
			'description': doc,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs a svn up on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid SVN repository',
			},
			'validate_config': CheckSyncConfig,
			'module_specific_options': (),
		}
	}
}
