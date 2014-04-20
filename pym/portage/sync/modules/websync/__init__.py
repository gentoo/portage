# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""WebRSync plug-in module for portage.
Performs a http download of a portage snapshot, verifies and
unpacks it to the repo location.
"""

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
	'description': __doc__,
	'provides':{
		'websync-module': {
			'name': "websync",
			'class': config_class,
			'description': __doc__,
			'functions': ['sync', 'new', 'exists'],
			'func_desc': {
				'sync': 'Performs an archived http download of the ' +
					'repository, then unpacks it.  Optionally it performs a ' +
					'gpg verification of the downloaded file(s)',
				'new': 'Creates the new repository at the specified location',
				'exists': 'Returns a boolean of whether the specified dir ' +
					'exists and is a valid repository',
			},
			'func_parameters': {
				'kwargs': {
					'type': dict,
					'description': 'Standard python **kwargs parameter format' +
						'Please refer to the sync modules specs at ' +
						'"https://wiki.gentoo.org:Project:Portage" for details',
					'required-keys': ['options', 'settings', 'logger', 'repo',
						'xterm_titles', 'spawn_kwargs'],
				},
			},
			'validate_config': CheckSyncConfig,
		},
	}
}
