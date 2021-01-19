# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Options plug-in module for repoman.
Performs option related actions on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'options',
	'description': doc,
	'provides':{
		'options-module': {
			'name': "options",
			'sourcefile': "options",
			'class': "Options",
			'description': doc,
			'functions': ['is_forced'],
			'func_desc': {
			},
			'mod_kwargs': ['options',
			],
			'func_kwargs': {
			},
			'module_runsIn': ['ebuilds'],
		},
	},
	'version': 1,
}
