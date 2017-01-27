# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Subversion (svn) plug-in module for portage.
Performs variaous subversion actions and checks on repositories."""
__doc__ = doc[:]


module_spec = {
	'name': 'svn',
	'description': doc,
	'provides':{
		'svn-module': {
			'name': "svn_status",
			'sourcefile': "status",
			'class': "Status",
			'description': doc,
			'functions': ['check', 'supports_gpg_sign', 'detect_conflicts'],
			'func_desc': {
			},
			'vcs_preserves_mtime': False,
			'needs_keyword_expansion': True,
		},
		'svn-changes': {
			'name': "svn_changes",
			'sourcefile': "changes",
			'class': "Changes",
			'description': doc,
			'functions': ['scan'],
			'func_desc': {
			},
		},
	}
}
