# -*- coding:utf-8 -*-

# import our initialized portage instance
from repoman._portage import portage
from repoman.modules.scan.scanbase import ScanBase


class ThirdPartyMirrors(ScanBase):

	def __init__(self, **kwargs):
		'''Class init

		@param repo_settings: settings instance
		@param qatracker: QATracker instance
		'''
		super(ThirdPartyMirrors, self).__init__(**kwargs)
		repo_settings = kwargs.get('repo_settings')
		self.qatracker = kwargs.get('qatracker')

		# TODO: Build a regex instead here, for the SRC_URI.mirror check.
		self.thirdpartymirrors = {}
		profile_thirdpartymirrors = repo_settings.repoman_settings.thirdpartymirrors().items()
		for mirror_alias, mirrors in profile_thirdpartymirrors:
			for mirror in mirrors:
				if not mirror.endswith("/"):
					mirror += "/"
				self.thirdpartymirrors[mirror] = mirror_alias

	def check(self, **kwargs):
		'''Check that URIs don't reference a server from thirdpartymirrors

		@param ebuild: Ebuild which we check (object).
		@param src_uri_error: boolean
		@returns: dictionary
		'''
		ebuild = kwargs.get('ebuild')
		if kwargs.get('src_uri_error'):
			return {'continue': True}
		for uri in portage.dep.use_reduce(
			ebuild.metadata["SRC_URI"], matchall=True, is_src_uri=True,
			eapi=ebuild.eapi, flat=True):
			contains_mirror = False
			for mirror, mirror_alias in self.thirdpartymirrors.items():
				if uri.startswith(mirror):
					contains_mirror = True
					break
			if not contains_mirror:
				continue

			new_uri = "mirror://%s/%s" % (mirror_alias, uri[len(mirror):])
			self.qatracker.add_error(
				"SRC_URI.mirror",
				"%s: '%s' found in thirdpartymirrors, use '%s'" % (
					ebuild.relative_path, mirror, new_uri))
		return {'continue': False}

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check])
