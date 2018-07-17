# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Check and fix problems in the world file."""
__doc__ = doc


module_spec = {
	'name': 'world',
	'description': doc,
	'provides':{
		'module1':{
			'name': "world",
			'sourcefile': "world",
			'class': "WorldHandler",
			'description': doc,
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
