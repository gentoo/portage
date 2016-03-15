
from repoman.modules.scan.scanbase import ScanBase


class UnusedCheck(ScanBase):

	def __init__(self, **kwargs):
		self.qatracker = kwargs.get('qatracker')

	def check(self, **kwargs):
		xpkg = kwargs.get('xpkg')
		muselist = kwargs.get('muselist')
		used_useflags = kwargs.get('used_useflags')
		# check if there are unused local USE-descriptions in metadata.xml
		# (unless there are any invalids, to avoid noise)
		if kwargs.get('validity_fuse'):
			for myflag in muselist.difference(used_useflags):
				self.qatracker.add_error(
					"metadata.warning",
					"%s/metadata.xml: unused local USE-description: '%s'"
					% (xpkg, myflag))
		return {'continue': False}

	@property
	def runInPkgs(self):
		return (False, [])

	@property
	def runInEbuilds(self):
		return (False, [])

	@property
	def runInFinal(self):
		return (True, [self.check])
