

import portage
from portage import os

from repoman._subprocess import repoman_popen



class VCSStatus(object):
	'''Determines the status of the vcs repositories
	to determine if files are not added'''

	def __init__(self, vcs_settings, checkdir, checkdir_relative, xpkg, qatracker):
		self.vcs_settings = vcs_settings
		self.vcs = vcs_settings.vcs
		self.eadded = []
		self.checkdir = checkdir
		self.checkdir_relative = checkdir_relative
		self.xpkg = xpkg
		self.qatracker = qatracker


	def check(self, check_not_added):
		if check_not_added:
			vcscheck = getattr(self, 'check_%s' % self.vcs)
			vcscheck()


	def post_git_hg(self, myf):
			for l in myf:
				if l[:-1][-7:] == ".ebuild":
					self.qatracker.add_error("ebuild.notadded",
						os.path.join(self.xpkg, os.path.basename(l[:-1])))
			myf.close()


	def check_git(self):
		myf = repoman_popen(
			"git ls-files --others %s" %
			(portage._shell_quote(self.checkdir_relative),))
		self.post_git_hg(myf)


	def check_hg(self):
		myf = repoman_popen(
			"hg status --no-status --unknown %s" %
			(portage._shell_quote(self.checkdir_relative),))
		self.post_git_hg(myf)


	def check_cvs(self):
			try:
				myf = open(self.checkdir + "/CVS/Entries", "r")
				myl = myf.readlines()
				myf.close()
			except IOError:
				self.qatracker.add_error("CVS/Entries.IO_error",
					self.checkdir + "/CVS/Entries")
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


	def check_svn(self):
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
				portage._shell_quote(self.checkdir))
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


	def check_bzr(self):
		try:
			myf = repoman_popen(
				"bzr ls -v --kind=file " +
				portage._shell_quote(self.checkdir))
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
		return  True
