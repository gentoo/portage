# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """CVS (cvs) plug-in module for portage.
Performs variaous CVS actions and checks on repositories."""
__doc__ = doc[:]


module_spec = {
	'name': 'cvs',
	'description': doc,
	'provides':{
		'cvs-status': {
			'name': "cvs_status",
			'sourcefile': "status",
			'class': "Status",
			'description': doc,
			'functions': ['check', 'supports_gpg_sign', 'detect_conflicts'],
			'func_desc': {
			},
			'vcs_preserves_mtime': True,
			'needs_keyword_expansion': True,
		},
		'cvs-changes': {
			'name': "cvs_changes",
			'sourcefile': "changes",
			'class': "Changes",
			'description': doc,
			'functions': ['scan'],
			'func_desc': {
			},
		},
	}
}
