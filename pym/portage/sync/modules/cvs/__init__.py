# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""CVS plug-in module for portage.
Performs a cvs up on repositories
"""


module_spec = {
	'name': 'cvs',
	'description': __doc__,
	'provides':{
		'module1': {
			'name': "cvs",
			'class': "CVSSync",
			'description': __doc__,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs a cvs up on the repository',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid CVS repository',
			},
			'func_parameters': {
				'kwargs': {
					'type': dict,
					'description': 'Standard python **kwargs parameter format' +
						'Please refer to the sync modules specs at ' +
						'"https://wiki.gentoo.org:Project:Portage" for details',
				},
			},
		}
	}
}
