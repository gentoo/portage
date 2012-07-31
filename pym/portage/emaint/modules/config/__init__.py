# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""'This emaint module provides checks and maintenance for:
Cleaning the emerge config tracker list
"""


module_spec = {
	'name': 'config',
	'description': "Provides functions to scan, check for and fix no " +\
		"longer installed config files in emerge's tracker file",
	'provides':{
		'module1': {
			'name': "cleanconfmem",
			'class': "CleanConfig",
			'description':  "Discard no longer installed config tracker entries",
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
