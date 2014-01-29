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
			'functions': ['sync',],
			'func_desc': {
				'sync', 'Performs a cvs up on the repository',
				}
			}
		}
	}
