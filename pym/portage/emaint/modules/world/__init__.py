# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Check and fix problems in the world file.
"""


module_spec = {
	'name': 'world',
	'description': __doc__,
	'provides':{
		'module1':{
			'name': "world",
			'class': "WorldHandler",
			'description': __doc__,
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
