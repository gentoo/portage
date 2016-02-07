'''
Mercurial module Changes class submodule
'''

from repoman.modules.vcs.changes import ChangesBase
from repoman._subprocess import repoman_popen


class Changes(ChangesBase):
	'''Class object to scan and hold the resultant data
	for all changes to process.
	'''

	vcs = 'hg'

	def __init__(self, options, repo_settings):
		'''Class init

		@param options: commandline options
		'''
		super(Changes, self).__init__(options, repo_settings)

	def _scan(self):
		'''VCS type scan function, looks for all detectable changes'''
		with repoman_popen("hg status --no-status --modified .") as f:
			changed = f.readlines()
		self.changed = ["./" + elem.rstrip() for elem in changed]
		del changed

		with repoman_popen("hg status --no-status --added .") as f:
			new = f.readlines()
		self.new = ["./" + elem.rstrip() for elem in new]
		del new

		with repoman_popen("hg status --no-status --removed .") as f:
			removed = f.readlines()
		self.removed = ["./" + elem.rstrip() for elem in removed]
		del removed

	@property
	def unadded(self):
		'''VCS method of getting the unadded files in the repository'''
		if self._unadded is not None:
			return self._unadded
		with repoman_popen("hg status --no-status --unknown .") as f:
			unadded = f.readlines()
		self._unadded = ["./" + elem.rstrip() for elem in unadded]
		del unadded
		return self._unadded

	@property
	def deleted(self):
		'''VCS method of getting the deleted files in the repository'''
		if self._deleted is not None:
			return self._deleted
		# Mercurial doesn't handle manually deleted files as removed from
		# the repository, so the user need to remove them before commit,
		# using "hg remove [FILES]"
		with repoman_popen("hg status --no-status --deleted .") as f:
			deleted = f.readlines()
		self._deleted = ["./" + elem.rstrip() for elem in deleted]
		del deleted
		return self._deleted

