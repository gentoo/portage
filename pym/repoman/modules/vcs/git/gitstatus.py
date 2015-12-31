
import re

from repoman._portage import portage
from portage import os
from repoman._subprocess import repoman_popen, repoman_getstatusoutput


class Status(object):

	def __init__(self, qatracker, eadded):
		self.qatracker = qatracker
		self.eadded = eadded

	def check(self, checkdir, checkdir_relative, xpkg):
		myf = repoman_popen(
			"git ls-files --others %s" %
			(portage._shell_quote(checkdir_relative),))
		for l in myf:
			if l[:-1][-7:] == ".ebuild":
				self.qatracker.add_error(
					"ebuild.notadded",
					os.path.join(xpkg, os.path.basename(l[:-1])))
		myf.close()
		return True

	@staticmethod
	def supports_gpg_sign():
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
	def detect_conflicts(options):
		return False

	@staticmethod
	def isVcsDir(dirname):
		return dirname in [".git"]

