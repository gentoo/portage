'''
Git module Status class submodule
'''

import re

from repoman._portage import portage
from portage import os
from repoman._subprocess import repoman_popen, repoman_getstatusoutput


class Status:
	'''Performs status checks on the git repository'''

	def __init__(self, qatracker, eadded):
		'''Class init

		@param qatracker: QATracker class instance
		@param eadded: list
		'''
		self.qatracker = qatracker
		self.eadded = eadded

	def check(self, checkdir, checkdir_relative, xpkg):
		'''Perform the git status check

		@param checkdir: string of the directory being checked
		@param checkdir_relative: string of the relative directory being checked
		@param xpkg: string of the package being checked
		@returns: boolean
		'''
		with repoman_popen(
			"git ls-files --others %s" %
			(portage._shell_quote(checkdir_relative),)) as myf:
			for l in myf:
				if l[:-1][-7:] == ".ebuild":
					self.qatracker.add_error(
						"ebuild.notadded",
						os.path.join(xpkg, os.path.basename(l[:-1])))
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
		status, cmd_output = \
			repoman_getstatusoutput("git --version")
		cmd_output = cmd_output.split()
		if cmd_output:
			version = re.match(r'^(\d+)\.(\d+)\.(\d+)', cmd_output[-1])
			if version is not None:
				version = [int(x) for x in version.groups()]
				if version[0] > 1 or \
					(version[0] == 1 and version[1] > 7) or \
					(version[0] == 1 and version[1] == 7 and version[2] >= 9):
					return True
		return False

	@staticmethod
	def isVcsDir(dirname):
		'''Does the directory belong to the vcs system

		@param dirname: string, directory name
		@returns: Boolean
		'''
		return dirname in [".git"]

