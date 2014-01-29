# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Rsync plug-in module for portage.
   Performs rsync transfers on repositories
"""


module_spec = {
	'name': 'rsync',
	'description': __doc__,
	'provides':{
		'module1': {
			'name': "rsync",
			'class': "RsyncSync",
			'description': __doc__,
			'functions': ['sync',],
			'func_desc': {
				'sync', 'Performs a rsync transfer on the repository'
				}
			}
		}
	}
