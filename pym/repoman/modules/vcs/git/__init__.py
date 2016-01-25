# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Git plug-in module for portage.
Performs variaous git actions and checks on repositories."""
__doc__ = doc[:]


module_spec = {
	'name': 'git',
	'description': doc,
	'provides':{
		'git-module': {
			'name': "gitstatus",
			'sourcefile': "gitstatus",
			'class': "Status",
			'description': doc,
			'functions': ['check', 'supports_gpg_sign', 'detect_conflicts'],
			'func_desc': {
			},
			'vcs_preserves_mtime': False,
		},
		'git-changes': {
			'name': "gitchanges",
			'sourcefile': "gitchanges",
			'class': "Changes",
			'description': doc,
			'functions': ['scan'],
			'func_desc': {
			},
		},
	}
}
