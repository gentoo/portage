# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from ....sync import _SUBMODULE_PATH_MAP

doc = """Check repos.conf settings and sync repositories."""
__doc__ = doc[:]

module_spec = {
	'name': 'sync',
	'description': doc,
	'provides':{
		'sync-module': {
			'name': "sync",
			'sourcefile': "sync",
			'class': "SyncRepos",
			'description': doc,
			'functions': ['allrepos', 'auto', 'repo'],
			'func_desc': {
				'repo': {
					"short": "-r", "long": "--repo",
					"help": "(sync module only): -r, --repo  Sync the specified repo",
					'status': "Syncing %s",
					'action': 'store',
					'func': 'repo',
					},
				'allrepos': {
					"short": "-A", "long": "--allrepos",
					"help": "(sync module only): -A, --allrepos  Sync all repos that have a sync-url defined",
					'status': "Syncing %s",
					'action': 'store_true',
					'dest': 'allrepos',
					'func': 'all_repos',
					},
				'auto': {
					"short": "-a", "long": "--auto",
					"help": "(sync module only): -a, --auto  Sync auto-sync enabled repos only",
					'status': "Syncing %s",
					'action': 'store_true',
					'dest': 'auto',
					'func': 'auto_sync',
					},
				},
			'opt_desc': {
				'sync-submodule': {
					"long": "--sync-submodule",
					"help": ("(sync module only): Restrict sync "
						"to the specified submodule(s)"),
					"choices": tuple(_SUBMODULE_PATH_MAP),
					"action": "append",
					"dest": "sync_submodule",
					},
				}
			}
		}
	}
