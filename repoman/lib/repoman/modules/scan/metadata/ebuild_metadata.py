# -*- coding:utf-8 -*-

'''Ebuild Metadata Checks'''

import re
import sys

from repoman.modules.scan.scanbase import ScanBase

from portage.dep import use_reduce

NON_ASCII_RE = re.compile(r'[^\x00-\x7f]')
URISCHEME_RE = re.compile(r'^[a-z][0-9a-z\-\.\+]+://')

class EbuildMetadata(ScanBase):

	def __init__(self, **kwargs):
		self.qatracker = kwargs.get('qatracker')
		self.repo_settings = kwargs.get('repo_settings')

	def invalidchar(self, **kwargs):
		ebuild = kwargs.get('ebuild').get()
		for k, v in ebuild.metadata.items():
			if not isinstance(v, str):
				continue
			m = NON_ASCII_RE.search(v)
			if m is not None:
				self.qatracker.add_error(
					"variable.invalidchar",
					"%s: %s variable contains non-ASCII "
					"character at position %s" %
					(ebuild.relative_path, k, m.start() + 1))
		return False

	def missing(self, **kwargs):
		ebuild = kwargs.get('ebuild').get()
		for pos, missing_var in enumerate(self.repo_settings.qadata.missingvars):
			if not ebuild.metadata.get(missing_var):
				if (kwargs.get('catdir') in ("acct-group", "acct-user", "virtual")
						and missing_var in ("HOMEPAGE", "LICENSE")):
					continue
				if ebuild.live_ebuild and missing_var == "KEYWORDS":
					continue
				myqakey = self.repo_settings.qadata.missingvars[pos] + ".missing"
				self.qatracker.add_error(myqakey, '%s/%s.ebuild'
					% (kwargs.get('xpkg'), kwargs.get('y_ebuild')))
		return False

	def virtual(self, **kwargs):
		ebuild = kwargs.get('ebuild').get()
		if kwargs.get('catdir') == "virtual":
			for var in ("HOMEPAGE", "LICENSE"):
				if ebuild.metadata.get(var):
					myqakey = var + ".virtual"
					self.qatracker.add_error(myqakey, ebuild.relative_path)
		return False

	def homepage_urischeme(self, **kwargs):
		ebuild = kwargs.get('ebuild').get()
		if kwargs.get('catdir') != "virtual":
			for homepage in use_reduce(ebuild.metadata["HOMEPAGE"],
				matchall=True,flat=True):
				if URISCHEME_RE.match(homepage) is None:
					self.qatracker.add_error(
						"HOMEPAGE.missingurischeme", ebuild.relative_path)
		return False

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.invalidchar, self.missing,
			self.virtual, self.homepage_urischeme])
