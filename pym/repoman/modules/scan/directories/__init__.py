# Copyright 2015-2016 Gentoo Foundation
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
		},
	}
}

