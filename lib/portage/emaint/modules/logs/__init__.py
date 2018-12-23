# Copyright 2005-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Check and clean old logs in the PORTAGE_LOGDIR."""
__doc__ = doc


module_spec = {
	'name': 'logs',
	'description': doc,
	'provides':{
		'module1': {
			'name': "logs",
			'sourcefile': "logs",
			'class': "CleanLogs",
			'description': doc,
			'functions': ['check','clean'],
			'func_desc': {
				'clean': {
					"short": "-C", "long": "--clean",
					"help": "Cleans out logs more than 7 days old (cleanlogs only)" + \
								 "   module-options: -t, -p",
					'status': "Cleaning %s",
					'action': 'store_true',
					'func': 'clean',
					},
				'time': {
					"short": "-t", "long": "--time",
					"help": "(cleanlogs only): -t, --time   Delete logs older than NUM of days",
					'status': "",
					'type': int,
					'dest': 'NUM',
					'func': 'clean'
					},
				'pretend': {
					"short": "-p", "long": "--pretend",
					"help": "(cleanlogs only): -p, --pretend   Output logs that would be deleted",
					'status': "",
					'action': 'store_true',
					'dest': 'pretend',
					'func': 'clean'
					}
				}
			}
		}
	}
