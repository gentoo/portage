


class Status(object):

	def __init__(self, qatracker, eadded):
		self.qatracker = qatracker
		self.eadded = eadded

	def check(self, checkdir, checkdir_relative, xpkg):
		return True

	@staticmethod
	def supports_gpg_sign():
		return False

	@staticmethod
	def detect_conflicts(options):
		return False

	@staticmethod
	def isVcsDir(dirname):
		return False

