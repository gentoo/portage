
from repoman._portage import portage
from portage import os
from repoman._subprocess import repoman_popen


class Status(object):

	def __init__(self, qatracker, eadded):
		self.qatracker = qatracker
		self.eadded = eadded

	def check(self, checkdir, checkdir_relative, xpkg):
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
		return False

	@staticmethod
	def supports_gpg_sign():
		return False

	@staticmethod
	def isVcsDir(dirname):
		return dirname in [".bzr"]
