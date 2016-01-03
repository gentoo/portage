# -*- coding:utf-8 -*-

'''Ebuild Metadata Checks'''

import re
import sys

if sys.hexversion >= 0x3000000:
	basestring = str

NON_ASCII_RE = re.compile(r'[^\x00-\x7f]')


class EbuildMetadata(object):

	def __init__(self, **kwargs):
		self.qatracker = kwargs.get('qatracker')

	def check(self, **kwargs):
		ebuild = kwargs.get('ebuild')
		for k, v in ebuild.metadata.items():
			if not isinstance(v, basestring):
				continue
			m = NON_ASCII_RE.search(v)
			if m is not None:
				self.qatracker.add_error(
					"variable.invalidchar",
					"%s: %s variable contains non-ASCII "
					"character at position %s" %
					(ebuild.relative_path, k, m.start() + 1))
		if ebuild.metadata.get("PROVIDE"):
			self.qatracker.add_error("virtual.oldstyle", ebuild.relative_path)

		return {'continue': False}

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.check])
