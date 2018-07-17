# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Check and clean the config tracker list for uninstalled packages."""
__doc__ = doc


module_spec = {
	'name': 'config',
	'description': doc,
	'provides':{
		'module1': {
			'name': "cleanconfmem",
			'sourcefile': "config",
			'class': "CleanConfig",
			'description': doc,
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
