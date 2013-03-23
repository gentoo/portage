# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Check and clean the config tracker list for uninstalled packages.
"""


module_spec = {
	'name': 'config',
	'description': __doc__,
	'provides':{
		'module1': {
			'name': "cleanconfmem",
			'class': "CleanConfig",
			'description': __doc__,
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
