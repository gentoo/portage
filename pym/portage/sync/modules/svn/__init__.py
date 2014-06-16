# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""SVN plug-in module for portage.
Performs a svn up on repositories
"""


from portage.localization import _
from portage.sync.config_checks import CheckSyncConfig
from portage.util import writemsg_level


module_spec = {
	'name': 'svn',
	'description': __doc__,
	'provides':{
		'svn-module': {
			'name': "svn",
			'class': "SVNSync",
			'description': __doc__,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs a svn up on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid SVN repository',
			},
			'validate_config': CheckSyncConfig,
		}
	}
}
