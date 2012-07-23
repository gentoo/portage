# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""'This emaint module provides checks and maintenance for:
Fixing problems with the "world" file.
"""


module_spec = {
	'name': 'world',
	'description': "Provides functions to scan, " +
		"check and fix problems in the world file",
	'provides':{
		'module1':{
			'name': "world",
			'class': "WorldHandler",
			'description':  "Fix problems in the world file",
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
