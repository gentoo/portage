
import portage


class ThirdPartyMirrors(object):

	def __init__(self, repoman_settings):
		# Build a regex from thirdpartymirrors for the SRC_URI.mirror check.
		self.thirdpartymirrors = {}
		for k, v in repoman_settings.thirdpartymirrors().items():
			for v in v:
				if not v.endswith("/"):
					v += "/"
		self.thirdpartymirrors[v] = k
		self.stats = 0
		self.fails = []


	def check(self, myaux, relative_path):
		# reset our stats in case this is a repeat run
		self.stats = 0
		self.fails = []
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
			self.stats += 1
			self.fails.append(
				"%s: '%s' found in thirdpartymirrors, use '%s'" %
				(relative_path, mirror, new_uri))
		return
