
'''ruby.py
Performs Ruby eclass checks
'''

from repoman.modules.scan.scanbase import ScanBase


class RubyEclassChecks(ScanBase):
	'''Performs checks for the usage of Ruby eclasses in ebuilds'''

	def __init__(self, **kwargs):
		'''
		@param qatracker: QATracker instance
		'''
		super(RubyEclassChecks, self).__init__(**kwargs)
		self.qatracker = kwargs.get('qatracker')
		self.repo_settings = kwargs.get('repo_settings')
		self.old_ruby_eclasses = ["ruby-ng", "ruby-fakegem", "ruby"]

	def check(self, **kwargs):
		'''Check ebuilds that inherit the ruby eclasses

		@param pkg: Package in which we check (object).
		@param ebuild: Ebuild which we check (object).
		@returns: dictionary
		'''
		pkg = kwargs.get('pkg').get()
		ebuild = kwargs.get('ebuild').get()
		is_inherited = lambda eclass: eclass in pkg.inherited
		is_old_ruby_eclass_inherited = filter(
			is_inherited, self.old_ruby_eclasses)

		if is_old_ruby_eclass_inherited:
			ruby_intersection = pkg.iuse.all.intersection(
				self.repo_settings.qadata.ruby_deprecated)

			if ruby_intersection:
				for myruby in ruby_intersection:
					self.qatracker.add_error(
						"IUSE.rubydeprecated",
						(ebuild.relative_path + ": Deprecated ruby target: %s")
						% myruby)
		return False

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check])
