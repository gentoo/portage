# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Perform package move updates for installed and binary packages."""
__doc__ = doc


module_spec = {
	'name': 'move',
	'description': doc,
	'provides':{
		'module1': {
			'name': "moveinst",
			'sourcefile': "move",
			'class': "MoveInstalled",
			'description': doc,
			'options': ['check', 'fix'],
			'functions': ['check', 'fix'],
			'func_desc': {
				}
			},
		'module2':{
			'name': "movebin",
			'sourcefile': "move",
			'class': "MoveBinary",
			'description': "Perform package move updates for binary packages",
			'functions': ['check', 'fix'],
			'func_desc': {
				}
			}
		}
	}
