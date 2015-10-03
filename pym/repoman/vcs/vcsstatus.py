# -*- coding:utf-8 -*-


# import our initialized portage instance
from repoman._portage import portage

from portage import os

from repoman._subprocess import repoman_popen


class VCSStatus(object):
	'''Determines the status of the vcs repositories
	to determine if files are not added'''

	def __init__(self, vcs_settings, qatracker):
		self.vcs_settings = vcs_settings
		self.vcs = vcs_settings.vcs
		self.eadded = []
		self.qatracker = qatracker

	def check(self, check_not_added, checkdir, checkdir_relative, xpkg):
		if self.vcs and check_not_added:
			vcscheck = getattr(self, 'check_%s' % self.vcs)
			vcscheck(checkdir, checkdir_relative, xpkg)

	def post_git_hg(self, myf, xpkg):
			for l in myf:
				if l[:-1][-7:] == ".ebuild":
					self.qatracker.add_error(
						"ebuild.notadded",
						os.path.join(xpkg, os.path.basename(l[:-1])))
			myf.close()

	def check_git(self, checkdir, checkdir_relative, xpkg):
		myf = repoman_popen(
			"git ls-files --others %s" %
			(portage._shell_quote(checkdir_relative),))
		self.post_git_hg(myf, xpkg)

	def check_hg(self, checkdir, checkdir_relative, xpkg):
		myf = repoman_popen(
			"hg status --no-status --unknown %s" %
			(portage._shell_quote(checkdir_relative),))
		self.post_git_hg(myf, xpkg)

	def check_cvs(self, checkdir, checkdir_relative, xpkg):
			try:
				myf = open(checkdir + "/CVS/Entries", "r")
				myl = myf.readlines()
				myf.close()
			except IOError:
				self.qatracker.add_error(
					"CVS/Entries.IO_error", checkdir + "/CVS/Entries")
				return True
			for l in myl:
				if l[0] != "/":
					continue
				splitl = l[1:].split("/")
				if not len(splitl):
					continue
				if splitl[0][-7:] == ".ebuild":
					self.eadded.append(splitl[0][:-7])
			return True

	def check_svn(self, checkdir, checkdir_relative, xpkg):
		try:
			myf = repoman_popen(
				"svn status --depth=files --verbose " +
				portage._shell_quote(self.checkdir))
			myl = myf.readlines()
			myf.close()
		except IOError:
			raise
		for l in myl:
			if l[:1] == "?":
				continue
			if l[:7] == '      >':
				# tree conflict, new in subversion 1.6
				continue
			l = l.split()[-1]
			if l[-7:] == ".ebuild":
				self.eadded.append(os.path.basename(l[:-7]))
		try:
			myf = repoman_popen(
				"svn status " +
				portage._shell_quote(checkdir))
			myl = myf.readlines()
			myf.close()
		except IOError:
			raise
		for l in myl:
			if l[0] == "A":
				l = l.rstrip().split(' ')[-1]
				if l[-7:] == ".ebuild":
					self.eadded.append(os.path.basename(l[:-7]))
		return True

	def check_bzr(self, checkdir, checkdir_relative, xpkg):
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
