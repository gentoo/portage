# Copyright 2015-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Use plug-in module for repoman.
Performs use flag checks on ebuilds."""
__doc__ = doc[:]


module_spec = {
	'name': 'use',
	'description': doc,
	'provides':{
		'use-module': {
			'name': "use_flags",
			'sourcefile': "use_flags",
			'class': "USEFlagChecks",
			'description': doc,
			'functions': ['check', 'getUsedUseFlags'],
			'func_desc': {
			},
			'mod_kwargs': ['qatracker', 'uselist',
			],
			'func_kwargs': {'pkg': None, 'xpkg': None, 'ebuild': None,
				'y_ebuild': None, 'muselist': None, 'ebuild_UsedUseFlags': 'set',
				'used_useflags': None,
			},
		},
	}
}

