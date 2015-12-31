
from repoman._portage import portage
from portage import os
from repoman._subprocess import repoman_popen

class Status(object):

	def __init__(self, qatracker, eadded):
		self.qatracker = qatracker
		self.eadded = eadded

	def check(self, checkdir, checkdir_relative, xpkg):
		myf = repoman_popen(
			"hg status --no-status --unknown %s" %
			(portage._shell_quote(checkdir_relative),))
		for l in myf:
			if l[:-1][-7:] == ".ebuild":
				self.qatracker.add_error(
					"ebuild.notadded",
					os.path.join(xpkg, os.path.basename(l[:-1])))
		myf.close()
		return True

	@staticmethod
	def detect_conflicts(options):
		return False

	@staticmethod
	def supports_gpg_sign():
		return False

	@staticmethod
	def isVcsDir(dirname):
		return dirname in [".hg"]
