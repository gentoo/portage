'''
None module Changes class submodule
'''

from repoman.modules.vcs.changes import ChangesBase


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'None'

	def __init__(self, options, repo_settings):
		'''Class init

		@param options: commandline options
		'''
		super(Changes, self).__init__(options, repo_settings)

	def scan(self):
		'''VCS type scan function, looks for all detectable changes'''
		pass

	def add_items(self, myautoadd):
		'''Nothing to add them to'''
		pass

	def commit(self, myfiles, commitmessagefile):
		commit_cmd = []
		# substitute a bogus vcs value for pretend output
		commit_cmd.append("pretend")
		commit_cmd.extend(self.vcs_settings.vcs_global_opts)
		commit_cmd.append("commit")
		commit_cmd.extend(self.vcs_settings.vcs_local_opts)
		commit_cmd.extend(["-F", commitmessagefile])
		commit_cmd.extend(f.lstrip("./") for f in myfiles)

		print("(%s)" % (" ".join(commit_cmd),))
		return 0
