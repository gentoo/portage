# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Perform package move updates for installed and binary packages.
"""


module_spec = {
	'name': 'move',
	'description': __doc__,
	'provides':{
		'module1': {
			'name': "moveinst",
			'class': "MoveInstalled",
			'description': __doc__,
			'options': ['check', 'fix'],
			'functions': ['check', 'fix'],
			'func_desc': {
				}
			},
		'module2':{
			'name': "movebin",
			'class': "MoveBinary",
			'description': "Perform package move updates for binary packages",
			'functions': ['check', 'fix'],
			'func_desc': {
				}
			}
		}
	}
