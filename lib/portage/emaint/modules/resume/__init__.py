# Copyright 2005-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

doc = """Check and fix problems in the resume and/or resume_backup files."""
__doc__ = doc


module_spec = {
	'name': 'resume',
	'description': doc,
	'provides':{
		'module1': {
			'name': "cleanresume",
			'sourcefile': "resume",
			'class': "CleanResume",
			'description':  "Discard emerge --resume merge lists",
			'functions': ['check', 'fix'],
			'func_desc': {}
			}
		}
	}
