# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

"""Check and fix problems in the resume and/or resume_backup files.
"""


module_spec = {
	'name': 'resume',
	'description': __doc__,
	'provides':{
		'module1': {
			'name': "cleanresume",
			'class': "CleanResume",
			'description':  "Discard emerge --resume merge lists",
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
