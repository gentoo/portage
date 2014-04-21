# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Check repos.conf settings and sync repositories.
"""


module_spec = {
	'name': 'sync',
	'description': __doc__,
	'provides':{
		'sync-module': {
			'name': "sync",
			'class': "SyncRepos",
			'description': __doc__,
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
				}
			}
		}
	}
