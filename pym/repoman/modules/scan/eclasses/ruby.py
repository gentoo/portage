
'''live.py
Performs Ruby eclass checks
'''

from repoman.qa_data import ruby_deprecated
from repoman.modules.scan.scanbase import ScanBase


class RubyEclassChecks(ScanBase):
	'''Performs checks for the usage of Ruby eclasses in ebuilds'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		'''
		super(RubyEclassChecks, self).__init__(**kwargs)
		self.qatracker = kwargs.get('qatracker')
		self.old_ruby_eclasses = ["ruby-ng", "ruby-fakegem", "ruby"]

	def check(self, **kwargs):
		pkg = kwargs.get('pkg')
		ebuild = kwargs.get('ebuild')
		is_inherited = lambda eclass: eclass in pkg.inherited
		is_old_ruby_eclass_inherited = filter(
			is_inherited, self.old_ruby_eclasses)

		if is_old_ruby_eclass_inherited:
			ruby_intersection = pkg.iuse.all.intersection(ruby_deprecated)

			if ruby_intersection:
				for myruby in ruby_intersection:
					self.qatracker.add_error(
						"IUSE.rubydeprecated",
						(ebuild.relative_path + ": Deprecated ruby target: %s")
						% myruby)
		return {'continue': False}

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check])
