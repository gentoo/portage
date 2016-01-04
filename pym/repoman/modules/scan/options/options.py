
from repoman.modules.scan.scanbase import ScanBase


class Options(ScanBase):

	def __init__(self, **kwargs):
		self.options = kwargs.get('options')

	def is_forced(self, **kwargs):
		if self.options.force:
			# The dep_check() calls are the most expensive QA test. If --force
			# is enabled, there's no point in wasting time on these since the
			# user is intent on forcing the commit anyway.
			return {'continue': True}
		return {'continue': False}

	@property
	def runInEbuilds(self):
		return (True, [self.is_forced])
