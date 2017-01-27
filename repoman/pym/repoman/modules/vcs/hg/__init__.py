# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Mercurial (hg) plug-in module for portage.
Performs variaous mercurial actions and checks on repositories."""
__doc__ = doc[:]


module_spec = {
	'name': 'hg',
	'description': doc,
	'provides':{
		'hg-module': {
			'name': "hg_status",
			'sourcefile': "status",
			'class': "Status",
			'description': doc,
			'functions': ['check', 'supports_gpg_sign', 'detect_conflicts'],
			'func_desc': {
			},
			'vcs_preserves_mtime': False,
			'needs_keyword_expansion': False,
		},
		'hg-changes': {
			'name': "hg_changes",
			'sourcefile': "changes",
			'class': "Changes",
			'description': doc,
			'functions': ['scan'],
			'func_desc': {
			},
		},
	}
}
