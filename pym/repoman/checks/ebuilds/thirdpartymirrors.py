
# import our initialized portage instance
from repoman._portage import portage


class ThirdPartyMirrors(object):

	def __init__(self, repoman_settings, qatracker):
		# TODO: Build a regex instead here, for the SRC_URI.mirror check.
		self.thirdpartymirrors = {}
		profile_thirdpartymirrors = repoman_settings.thirdpartymirrors().items()
		for mirror_alias, mirrors in profile_thirdpartymirrors:
			for mirror in mirrors:
				if not mirror.endswith("/"):
					mirror += "/"
				self.thirdpartymirrors[mirror] = mirror_alias

		self.qatracker = qatracker

	def check(self, myaux, relative_path):
		# Check that URIs don't reference a server from thirdpartymirrors.
		for uri in portage.dep.use_reduce(
			myaux["SRC_URI"], matchall=True, is_src_uri=True,
			eapi=myaux["EAPI"], flat=True):
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
					relative_path, mirror, new_uri))
		return
