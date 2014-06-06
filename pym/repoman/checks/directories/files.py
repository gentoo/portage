
'''repoman/checks/diretories/files.py

'''

import io

from portage import _encodings, _unicode_encode
from portage import os

from repoman.vcs.vcs import vcs_new_changed


class FileChecks(object):

	def __init__(
		self, qatracker, repoman_settings, repo_settings, portdb, vcs_settings):
		'''
		@param qatracker: QATracker instance
		@param repoman_settings: settings instance
		@param repo_settings: repository settings instance
		@param portdb: portdb instance
		'''
		self.portdb = portdb
		self.qatracker = qatracker
		self.repo_settings = repo_settings
		self.repoman_settings = repoman_settings
		self.vcs_settings = vcs_settings

	def check(self, checkdir, checkdirlist, checkdir_relative, changed, new):
		'''Checks the ebuild sources and files for errors

		@param xpkg: the pacakge being checked
		@param checkdir: string, directory path
		@param checkdir_relative: repolevel determined path
		'''
		for y_file in checkdirlist:
			index = self.repo_settings.repo_config.find_invalid_path_char(y_file)
			if index != -1:
				y_relative = os.path.join(checkdir_relative, y_file)
				invcs = self.vcs_settings.vcs is not None
				inchangeset = vcs_new_changed(y_relative, changed, new)
				if invcs and not inchangeset:
					# If the file isn't in the VCS new or changed set, then
					# assume that it's an irrelevant temporary file (Manifest
					# entries are not generated for file names containing
					# prohibited characters). See bug #406877.
					index = -1
			if index != -1:
				self.qatracker.add_error(
					"file.name",
					"%s/%s: char '%s'" % (checkdir, y_file, y_file[index]))

			if not (
				y_file in ("ChangeLog", "metadata.xml")
				or y_file.endswith(".ebuild")):
				continue
			f = None
			try:
				line = 1
				f = io.open(
					_unicode_encode(
						os.path.join(checkdir, y_file),
						encoding=_encodings['fs'], errors='strict'),
					mode='r', encoding=_encodings['repo.content'])
				for l in f:
					line += 1
			except UnicodeDecodeError as ue:
				s = ue.object[:ue.start]
				l2 = s.count("\n")
				line += l2
				if l2 != 0:
					s = s[s.rfind("\n") + 1:]
				self.qatracker.add_error(
					"file.UTF8", "%s/%s: line %i, just after: '%s'" % (
						checkdir, y_file, line, s))
			finally:
				if f is not None:
					f.close()
		return
