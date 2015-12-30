# -*- coding:utf-8 -*-

'''fetches.py
Performs the src_uri fetchlist and files checks
'''

from stat import S_ISDIR

# import our initialized portage instance
from repoman._portage import portage

from portage import os

from repoman.modules.vcs.vcs import vcs_new_changed


class FetchChecks(object):
	'''Performs checks on the files needed for the ebuild'''

	def __init__(
		self, qatracker, repo_settings, portdb, vcs_settings):
		'''
		@param qatracker: QATracker instance
		@param repoman_settings: settings instance
		@param repo_settings: repository settings instance
		@param portdb: portdb instance
		'''
		self.portdb = portdb
		self.qatracker = qatracker
		self.repo_settings = repo_settings
		self.repoman_settings = repo_settings.repoman_settings
		self.vcs_settings = vcs_settings

	def check(self, xpkg, checkdir, checkdir_relative, mychanged, mynew):
		'''Checks the ebuild sources and files for errors

		@param xpkg: the pacakge being checked
		@param checkdir: string, directory path
		@param checkdir_relative: repolevel determined path
		'''
		_digests = self.digests(checkdir)
		fetchlist_dict = portage.FetchlistDict(
			checkdir, self.repoman_settings, self.portdb)
		myfiles_all = []
		self.src_uri_error = False
		for mykey in fetchlist_dict:
			try:
				myfiles_all.extend(fetchlist_dict[mykey])
			except portage.exception.InvalidDependString as e:
				self.src_uri_error = True
				try:
					self.portdb.aux_get(mykey, ["SRC_URI"])
				except KeyError:
					# This will be reported as an "ebuild.syntax" error.
					pass
				else:
					self.qatracker.add_error(
						"SRC_URI.syntax", "%s.ebuild SRC_URI: %s" % (mykey, e))
		del fetchlist_dict
		if not self.src_uri_error:
			# This test can produce false positives if SRC_URI could not
			# be parsed for one or more ebuilds. There's no point in
			# producing a false error here since the root cause will
			# produce a valid error elsewhere, such as "SRC_URI.syntax"
			# or "ebuild.sytax".
			myfiles_all = set(myfiles_all)
			for entry in _digests:
				if entry not in myfiles_all:
					self.qatracker.add_error("digest.unused", checkdir + "::" + entry)
			for entry in myfiles_all:
				if entry not in _digests:
					self.qatracker.add_error("digest.missing", checkdir + "::" + entry)
		del myfiles_all

		if os.path.exists(checkdir + "/files"):
			filesdirlist = os.listdir(checkdir + "/files")

			# Recurse through files directory, use filesdirlist as a stack;
			# appending directories as needed,
			# so people can't hide > 20k files in a subdirectory.
			while filesdirlist:
				y = filesdirlist.pop(0)
				relative_path = os.path.join(xpkg, "files", y)
				full_path = os.path.join(self.repo_settings.repodir, relative_path)
				try:
					mystat = os.stat(full_path)
				except OSError as oe:
					if oe.errno == 2:
						# don't worry about it.  it likely was removed via fix above.
						continue
					else:
						raise oe
				if S_ISDIR(mystat.st_mode):
					# !!! VCS "portability" alert!  Need some function isVcsDir() or alike !!!
					if y == "CVS" or y == ".svn":
						continue
					for z in os.listdir(checkdir + "/files/" + y):
						if z == "CVS" or z == ".svn":
							continue
						filesdirlist.append(y + "/" + z)
				# Current policy is no files over 20 KiB, these are the checks.
				# File size between 20 KiB and 60 KiB causes a warning,
				# while file size over 60 KiB causes an error.
				elif mystat.st_size > 61440:
					self.qatracker.add_error(
						"file.size.fatal", "(%d KiB) %s/files/%s" % (
							mystat.st_size // 1024, xpkg, y))
				elif mystat.st_size > 20480:
					self.qatracker.add_error(
						"file.size", "(%d KiB) %s/files/%s" % (
							mystat.st_size // 1024, xpkg, y))

				index = self.repo_settings.repo_config.find_invalid_path_char(y)
				if index != -1:
					y_relative = os.path.join(checkdir_relative, "files", y)
					if self.vcs_settings.vcs is not None \
						and not vcs_new_changed(y_relative, mychanged, mynew):
						# If the file isn't in the VCS new or changed set, then
						# assume that it's an irrelevant temporary file (Manifest
						# entries are not generated for file names containing
						# prohibited characters). See bug #406877.
						index = -1
				if index != -1:
					self.qatracker.add_error(
						"file.name",
						"%s/files/%s: char '%s'" % (checkdir, y, y[index]))

	def digests(self, checkdir):
		'''Returns the freshly loaded digests'''
		mf = self.repoman_settings.repositories.get_repo_for_location(
			os.path.dirname(os.path.dirname(checkdir)))
		mf = mf.load_manifest(checkdir, self.repoman_settings["DISTDIR"])
		_digests = mf.getTypeDigests("DIST")
		del mf
		return _digests
