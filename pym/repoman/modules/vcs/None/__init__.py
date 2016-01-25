# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """None (non vcs type) plug-in module for portage.
Performs various git actions and checks on repositories."""
__doc__ = doc[:]


module_spec = {
	'name': 'None',
	'description': doc,
	'provides':{
		'None-module': {
			'name': "Nonestatus",
			'sourcefile': "Nonestatus",
			'class': "Status",
			'description': doc,
			'functions': ['check', 'supports_gpg_sign', 'detect_conflicts'],
			'func_desc': {
			},
			'vcs_preserves_mtime': False,
		},
		'None-changes': {
			'name': "Nonechanges",
			'sourcefile': "Nonechanges",
			'class': "Changes",
			'description': doc,
			'functions': ['scan'],
			'func_desc': {
			},
		},
	}
}
