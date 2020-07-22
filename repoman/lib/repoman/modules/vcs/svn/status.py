'''
Subversion module Status class submodule
'''

import logging
import subprocess
import sys

from repoman._portage import portage
from portage import os
from portage.const import BASH_BINARY
from portage.output import red, green
from portage import _unicode_encode, _unicode_decode

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
				"svn status --depth=files --verbose " +
				portage._shell_quote(checkdir))
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

	@staticmethod
	def detect_conflicts(options):
		"""Determine if the checkout has problems like cvs conflicts.

		If you want more vcs support here just keep adding if blocks...
		This could be better.

		TODO(antarus): Also this should probably not call sys.exit() as
		repoman is run on >1 packages and one failure should not cause
		subsequent packages to fail.

		Args:
			vcs - A string identifying the version control system in use
		Returns: boolean
			(calls sys.exit on fatal problems)
		"""

		cmd = "svn status -u 2>&1 | egrep -v '^.  +.*/digest-[^/]+' | head -n-1"
		msg = ("Performing a %s with a little magic grep to check for updates."
				% green("svn status -u"))

		logging.info(msg)
		# Use Popen instead of getstatusoutput(), in order to avoid
		# unicode handling problems (see bug #310789).
		args = [BASH_BINARY, "-c", cmd]
		args = [_unicode_encode(x) for x in args]
		proc = subprocess.Popen(
			args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		out = _unicode_decode(proc.communicate()[0])
		proc.wait()
		mylines = out.splitlines()
		myupdates = []
		for line in mylines:
			if not line:
				continue

			# [ ] Unmodified (SVN)	[U] Updates		[P] Patches
			# [M] Modified			[A] Added		[R] Removed / Replaced
			# [D] Deleted
			if line[0] not in " UPMARD":
				# Stray Manifest is fine, we will readd it anyway.
				if line[0] == '?' and line[1:].lstrip() == 'Manifest':
					continue
				logging.error(red(
					"!!! Please fix the following issues reported "
					"from cvs: %s" % green("(U,P,M,A,R,D are ok)")))
				logging.error(red(
					"!!! Note: This is a pretend/no-modify pass..."))
				logging.error(out)
				sys.exit(1)
			elif line[8] == '*':
				myupdates.append(line[9:].lstrip(" 1234567890"))

		if myupdates:
			logging.info(green("Fetching trivial updates..."))
			if options.pretend:
				logging.info("(svn update " + " ".join(myupdates) + ")")
				retval = os.EX_OK
			else:
				retval = os.system("svn update " + " ".join(myupdates))
			if retval != os.EX_OK:
				logging.fatal("!!! svn exited with an error. Terminating.")
				sys.exit(retval)
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
		return dirname in [".svn"]
