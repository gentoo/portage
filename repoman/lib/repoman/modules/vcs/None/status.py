'''
None (non-VCS) module Status class submodule
'''


class Status:
	'''Performs status checks on the svn repository'''

	def __init__(self, qatracker, eadded):
		'''Class init

		@param qatracker: QATracker class instance
		@param eadded: list
		'''
		self.qatracker = qatracker
		self.eadded = eadded

	def check(self, checkdir, checkdir_relative, xpkg):
		'''Perform the svn status check

		@param checkdir: string of the directory being checked
		@param checkdir_relative: string of the relative directory being checked
		@param xpkg: string of the package being checked
		@returns: boolean
		'''
		return True

	@staticmethod
	def detect_conflicts(options):
		'''Are there any merge conflicts present in the VCS tracking system

		@param options: command line options
		@returns: Boolean
		'''
		return False

	@staticmethod
	def supports_gpg_sign():
		'''Does this vcs system support gpg commit signatures

		@returns: Boolean
		'''
		return False

	@staticmethod
	def isVcsDir(dirname):
		'''Is the directory belong to the vcs system

		@param dirname: string, directory name
		@returns: Boolean
		'''
		return False

