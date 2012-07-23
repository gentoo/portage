# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""'This emaint module provides checks and maintenance for:
  1) "Performing package move updates for installed packages",
  2)"Perform package move updates for binary packages"
"""


module_spec = {
	'name': 'move',
	'description': "Provides functions to check for and move packages " +\
		"either installed or binary packages stored on this system",
	'provides':{
		'module1': {
			'name': "moveinst",
			'class': "MoveInstalled",
			'description': "Perform package move updates for installed packages",
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
