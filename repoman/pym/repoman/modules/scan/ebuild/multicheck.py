
'''multicheck.py
Perform  multiple different checks on an ebuild
'''

import io

from portage import _encodings, _unicode_encode

from repoman.modules.scan.scanbase import ScanBase
from repoman.modules.linechecks.controller import LineCheckController


class MultiCheck(ScanBase):
	'''Class to run multiple different checks on an ebuild'''

	def __init__(self, **kwargs):
		'''Class init

		@param qatracker: QATracker instance
		@param options: the run time cli options
		'''
		self.qatracker = kwargs.get('qatracker')
		self.options = kwargs.get('options')
		self.controller = LineCheckController(
				kwargs.get('repo_settings'),
				kwargs.get('linechecks')
				)
		self.controller.checks_init(self.options.experimental_inherit == 'y')

	def check(self, **kwargs):
		'''Check the ebuild for utf-8 encoding

		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		@returns: dictionary
		'''
		ebuild = kwargs.get('ebuild').get()
		pkg = kwargs.get('pkg').get()
		try:
			# All ebuilds should have utf_8 encoding.
			f = io.open(
				_unicode_encode(ebuild.full_path, encoding=_encodings['fs'],
					errors='strict'),
				mode='r', encoding=_encodings['repo.content'])
			try:
				for check_name, e in self.controller.run_checks(f, pkg):
					self.qatracker.add_error(
						check_name, ebuild.relative_path + ': %s' % e)
			finally:
				f.close()
		except UnicodeDecodeError:
			# A file.UTF8 failure will have already been recorded.
			pass
		return False

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check])
