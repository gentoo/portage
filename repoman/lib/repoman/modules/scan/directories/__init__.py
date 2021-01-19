# Copyright 2015-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

doc = """Directories plug-in module for repoman.
Performs an FilesChecks check on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'directories',
	'description': doc,
	'provides':{
		'directories-module': {
			'name': "files",
			'sourcefile': "files",
			'class': "FileChecks",
			'description': doc,
			'functions': ['check'],
			'func_kwargs': {
			},
			'mod_kwargs': ['portdb', 'qatracker', 'repo_settings', 'vcs_settings',
			],
			'func_kwargs': {
				'changed': (None, None),
				'checkdir': (None, None),
				'checkdirlist': (None, None),
				'checkdir_relative': (None, None),
			},
			'module_runsIn': ['pkgs'],
		},
		'mtime-module': {
			'name': "mtime",
			'sourcefile': "mtime",
			'class': "MtimeChecks",
			'description': doc,
			'functions': ['check'],
			'func_kwargs': {
			},
			'mod_kwargs': ['vcs_settings',
			],
			'func_kwargs': {
				'changed': (None, None),
				'ebuild': (None, None),
				'pkg': (None, None),
			},
			'module_runsIn': ['ebuilds'],
		},
	},
	'version': 1,
}
