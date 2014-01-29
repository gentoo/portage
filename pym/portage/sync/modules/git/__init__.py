# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Git plug-in module for portage.
Performs a git pull on repositories
"""


module_spec = {
	'name': 'git',
	'description': __doc__,
	'provides':{
		'module1': {
			'name': "git",
			'class': "GitSync",
			'description': __doc__,
			'functions': ['sync',],
			'func_desc': {
				'sync', 'Performs a git pull on the repository',
				}
			}
		}
	}
