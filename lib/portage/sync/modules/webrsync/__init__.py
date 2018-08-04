# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """WebRSync plug-in module for portage.
Performs a http download of a portage snapshot, verifies and
unpacks it to the repo location."""
__doc__ = doc[:]


import os

from portage.sync.config_checks import CheckSyncConfig


DEFAULT_CLASS = "WebRsync"
AVAILABLE_CLASSES = [ "WebRsync",  "PyWebsync"]
options = {"1": "WebRsync", "2": "PyWebsync"}


config_class = DEFAULT_CLASS
try:
	test_param = os.environ["TESTIT"]
	if test_param in options:
		config_class = options[test_param]
except KeyError:
	pass


module_spec = {
	'name': 'webrsync',
	'description': doc,
	'provides':{
		'webrsync-module': {
			'name': "webrsync",
			'sourcefile': "webrsync",
			'class': config_class,
			'description': doc,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs an archived http download of the ' +
					'repository, then unpacks it.  Optionally it performs a ' +
					'gpg verification of the downloaded file(s)',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid repository',
			},
			'validate_config': CheckSyncConfig,
			'module_specific_options': (
				'sync-webrsync-delta',
				'sync-webrsync-keep-snapshots',
				'sync-webrsync-verify-signature',
			),
		},
	}
}
