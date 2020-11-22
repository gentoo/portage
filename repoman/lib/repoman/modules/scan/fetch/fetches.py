# -*- coding:utf-8 -*-

'''fetches.py
Performs the src_uri fetchlist and files checks
'''

from stat import S_ISDIR

# import our initialized portage instance
from repoman._portage import portage
from repoman.modules.vcs.vcs import vcs_new_changed
from repoman.modules.scan.scanbase import ScanBase

from portage import os


class FetchChecks(ScanBase):
	'''Performs checks on the files needed for the ebuild'''

	def __init__(self, **kwargs):
		'''
		@param portdb: portdb instance
		@param qatracker: QATracker instance
		@param repo_settings: repository settings instance
		@param vcs_settings: VCSSettings instance
		'''
		super(FetchChecks, self).__init__(**kwargs)
		self.portdb = kwargs.get('portdb')
		self.qatracker = kwargs.get('qatracker')
		self.repo_settings = kwargs.get('repo_settings')
		self.repoman_settings = self.repo_settings.repoman_settings
		self.vcs_settings = kwargs.get('vcs_settings')
		self._src_uri_error = False

		# TODO: Build a regex instead here, for the SRC_URI.mirror check.
		self.thirdpartymirrors = {}
		profile_thirdpartymirrors = self.repo_settings.repoman_settings.thirdpartymirrors().items()
		for mirror_alias, mirrors in profile_thirdpartymirrors:
			# Skip thirdpartymirrors that do not list more than one mirror
			# anymore. There is no point in using mirror:// there and this
			# means that the thirdpartymirrors entry will most likely
			# be removed anyway.
			if len(mirrors) <= 1:
				continue
			for mirror in mirrors:
				if not mirror.endswith("/"):
					mirror += "/"
				self.thirdpartymirrors[mirror] = mirror_alias

	def check(self, **kwargs):
		'''Checks the ebuild sources and files for errors

		@param xpkg: the pacakge being checked
		@param checkdir: string, directory path
		@param checkdir_relative: repolevel determined path
		@returns: boolean
		'''
		xpkg = kwargs.get('xpkg')
		checkdir = kwargs.get('checkdir')
		checkdir_relative = kwargs.get('checkdir_relative')
		changed = kwargs.get('changed').changed
		new = kwargs.get('changed').new
		_digests = self.digests(checkdir)
		fetchlist_dict = portage.FetchlistDict(
			checkdir, self.repoman_settings, self.portdb)
		myfiles_all = []
		self._src_uri_error = False
		for mykey in fetchlist_dict:
			try:
				myfiles_all.extend(fetchlist_dict[mykey])
			except portage.exception.InvalidDependString as e:
				self._src_uri_error = True
				try:
					self.portdb.aux_get(mykey, ["SRC_URI"])
				except KeyError:
					# This will be reported as an "ebuild.syntax" error.
					pass
				else:
					self.qatracker.add_error(
						"SRC_URI.syntax", "%s.ebuild SRC_URI: %s" % (mykey, e))
		del fetchlist_dict
		if not self._src_uri_error:
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
					if self.vcs_settings.status.isVcsDir(y):
						continue
					for z in os.listdir(checkdir + "/files/" + y):
						if self.vcs_settings.status.isVcsDir(z):
							continue
						filesdirlist.append(y + "/" + z)
				# Current policy is no files over 20 KiB, these are the checks.
				# File size over 20 KiB causes an error.
				elif mystat.st_size > 20480:
					self.qatracker.add_error(
						"file.size", "(%d KiB) %s/files/%s" % (
							mystat.st_size // 1024, xpkg, y))
				elif mystat.st_size == 0:
					self.qatracker.add_error(
						"file.empty", "%s/files/%s" % (xpkg, y))

				index = self.repo_settings.repo_config.find_invalid_path_char(y)
				if index != -1:
					y_relative = os.path.join(checkdir_relative, "files", y)
					if self.vcs_settings.vcs is not None \
						and not vcs_new_changed(y_relative, changed, new):
						# If the file isn't in the VCS new or changed set, then
						# assume that it's an irrelevant temporary file (Manifest
						# entries are not generated for file names containing
						# prohibited characters). See bug #406877.
						index = -1
				if index != -1:
					self.qatracker.add_error(
						"file.name",
						"%s/files/%s: char '%s'" % (checkdir, y, y[index]))
		return False

	def digests(self, checkdir):
		'''Returns the freshly loaded digests

		@param checkdir: string, directory path
		'''
		mf = self.repoman_settings.repositories.get_repo_for_location(
			os.path.dirname(os.path.dirname(checkdir)))
		mf = mf.load_manifest(checkdir, self.repoman_settings["DISTDIR"])
		_digests = mf.getTypeDigests("DIST")
		del mf
		return _digests

	def check_mirrors(self, **kwargs):
		'''Check that URIs don't reference a server from thirdpartymirrors

		@param ebuild: Ebuild which we check (object).
		@returns: boolean
		'''
		ebuild = kwargs.get('ebuild').get()

		for uri in portage.dep.use_reduce(
			ebuild.metadata["SRC_URI"], matchall=True, is_src_uri=True,
			eapi=ebuild.eapi, flat=True):
			contains_mirror = False
			for mirror, mirror_alias in self.thirdpartymirrors.items():
				if uri.startswith(mirror):
					contains_mirror = True
					break
			if not contains_mirror:
				continue

			new_uri = "mirror://%s/%s" % (mirror_alias, uri[len(mirror):])
			self.qatracker.add_error(
				"SRC_URI.mirror",
				"%s: '%s' found in thirdpartymirrors, use '%s'" % (
					ebuild.relative_path, mirror, new_uri))
		return False

	@property
	def runInPkgs(self):
		'''Package level scans'''
		return (True, [self.check])

	@property
	def runInEbuilds(self):
		'''Ebuild level scans'''
		return (True, [self.check_mirrors])
