
from repoman.modules.scan.scanbase import ScanBase


class Options(ScanBase):

	def __init__(self, **kwargs):
		'''Class init function

		@param options: argparse options instance
		'''
		self.options = kwargs.get('options')

	def is_forced(self, **kwargs):
		'''Simple boolean function to trigger a skip past some additional checks

		@returns: dictionary
		'''
		if self.options.force:
			# The dep_check() calls are the most expensive QA test. If --force
			# is enabled, there's no point in wasting time on these since the
			# user is intent on forcing the commit anyway.
			return True
		return False

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.is_forced])
