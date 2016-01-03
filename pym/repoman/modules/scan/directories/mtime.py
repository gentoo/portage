

class MtimeChecks(object):

	def __init__(self, **kwargs):
		self.vcs_settings = kwargs.get('vcs_settings')

	def check(self, **kwargs):
		ebuild = kwargs.get('ebuild')
		changed = kwargs.get('changed')
		pkg = kwargs.get('pkg')
		if not self.vcs_settings.vcs_preserves_mtime:
			if ebuild.ebuild_path not in changed.new_ebuilds and \
					ebuild.ebuild_path not in changed.ebuilds:
				pkg.mtime = None
		return {'continue': False}

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (True, [self.check])
