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
			'name': "None_status",
			'sourcefile': "status",
			'class': "Status",
			'description': doc,
			'functions': ['check', 'supports_gpg_sign', 'detect_conflicts'],
			'func_desc': {
			},
			'vcs_preserves_mtime': False,
			'needs_keyword_expansion': False,
		},
		'None-changes': {
			'name': "None_changes",
			'sourcefile': "changes",
			'class': "Changes",
			'description': doc,
			'functions': ['scan'],
			'func_desc': {
			},
		},
	}
}
