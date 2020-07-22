'''
Bazaar module Status class submodule
'''

from repoman._portage import portage
from portage import os
from repoman._subprocess import repoman_popen


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
		try:
			myf = repoman_popen(
				"bzr ls -v --kind=file " +
				portage._shell_quote(checkdir))
			myl = myf.readlines()
			myf.close()
		except IOError:
			raise
		for l in myl:
			if l[1:2] == "?":
				continue
			l = l.split()[-1]
			if l[-7:] == ".ebuild":
				self.eadded.append(os.path.basename(l[:-7]))
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
		'''Does the directory belong to the vcs system

		@param dirname: string, directory name
		@returns: Boolean
		'''
		return dirname in [".bzr"]
