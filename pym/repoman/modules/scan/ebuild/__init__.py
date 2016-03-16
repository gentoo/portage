# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Ebuild plug-in module for repoman.
Performs an IsEbuild check on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'ebuild',
	'description': doc,
	'provides':{
		'isebuild-module': {
			'name': "isebuild",
			'sourcefile': "isebuild",
			'class': "IsEbuild",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['portdb', 'qatracker', 'repo_settings'
			],
			'func_kwargs': {
			},
		},
		'ebuild-module': {
			'name': "ebuild",
			'sourcefile': "ebuild",
			'class': "Ebuild",
			'description': doc,
			'functions': ['check'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker', 'repo_settings', 'vcs_settings', 'checks',
			],
			'func_kwargs': {
			},
		},
		'multicheck-module': {
			'name': "multicheck",
			'sourcefile': "multicheck",
			'class': "MultiCheck",
			'description': doc,
			'functions': ['check'],
			'func_kwargs': {
			},
			'mod_kwargs': ['qatracker', 'options'
			],
			'func_kwargs': {
			},
		},
	}
}

