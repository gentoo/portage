# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Bazaar (bzr) plug-in module for portage.
Performs variaous Bazaar actions and checks on repositories."""
__doc__ = doc[:]


module_spec = {
	'name': 'bzr',
	'description': doc,
	'provides':{
		'bzr-module': {
			'name': "bzr_status",
			'sourcefile': "status",
			'class': "Status",
			'description': doc,
			'functions': ['check', 'supports_gpg_sign', 'detect_conflicts'],
			'func_desc': {
			},
			'vcs_preserves_mtime': True,
			'needs_keyword_expansion': False,
		},
		'bzr-changes': {
			'name': "bzr_changes",
			'sourcefile': "changes",
			'class': "Changes",
			'description': doc,
			'functions': ['scan'],
			'func_desc': {
			},
		},
	}
}
