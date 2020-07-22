'''
CVS module Status class submodule
'''

import logging
import subprocess
import sys

from repoman._portage import portage
from portage import os
from portage.const import BASH_BINARY
from portage.output import red, green
from portage import _unicode_encode, _unicode_decode


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

	@staticmethod
	def detect_conflicts(options):
		"""Determine if the checkout has cvs conflicts.

		TODO(antarus): Also this should probably not call sys.exit() as
		repoman is run on >1 packages and one failure should not cause
		subsequent packages to fail.

		Returns:
			None (calls sys.exit on fatal problems)
		"""

		cmd = (r"cvs -n up 2>/dev/null | "
				r"egrep '^[^\?] .*' | "
				r"egrep -v '^. .*/digest-[^/]+|^cvs server: .* -- ignored$'")
		msg = ("Performing a %s with a little magic grep to check for updates."
				% green("cvs -n up"))

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
			elif line[0] in "UP":
				myupdates.append(line[2:])

		if myupdates:
			logging.info(green("Fetching trivial updates..."))
			if options.pretend:
				logging.info("(cvs update " + " ".join(myupdates) + ")")
				retval = os.EX_OK
			else:
				retval = os.system("cvs update " + " ".join(myupdates))
			if retval != os.EX_OK:
				logging.fatal("!!! cvs exited with an error. Terminating.")
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
		return dirname in ["CVS"]
