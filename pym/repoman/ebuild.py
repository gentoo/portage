

from portage import os


class Ebuild(object):
	'''Class to run primary checks on ebuilds'''

	def __init__(
		self, repo_settings, repolevel, pkgdir, catdir, vcs_settings, x, y):
		self.vcs_settings = vcs_settings
		self.relative_path = os.path.join(x, y + ".ebuild")
		self.full_path = os.path.join(repo_settings.repodir, self.relative_path)
		self.ebuild_path = y + ".ebuild"
		if repolevel < 3:
			self.ebuild_path = os.path.join(pkgdir, self.ebuild_path)
		if repolevel < 2:
			self.ebuild_path = os.path.join(catdir, self.ebuild_path)
		self.ebuild_path = os.path.join(".", self.ebuild_path)

	def untracked(self, check_ebuild_notadded, y, eadded):
		do_check = self.vcs_settings.vcs in ("cvs", "svn", "bzr")
		really_notadded = check_ebuild_notadded and y not in eadded

		if do_check and really_notadded:
			# ebuild not added to vcs
			return True
		return False
