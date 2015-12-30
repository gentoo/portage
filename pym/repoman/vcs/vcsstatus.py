# -*- coding:utf-8 -*-


class VCSStatus(object):
	'''Determines the status of the vcs repositories
	to determine if files are not added'''

	def __init__(self, vcs_settings):
		self.vcs_settings = vcs_settings

	def check(self, check_not_added, checkdir, checkdir_relative, xpkg):
		if self.vcs_settings.vcs and check_not_added:
			self.vcs_settings.status.check(checkdir, checkdir_relative, xpkg)

