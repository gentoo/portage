# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.output import teal
from portage import os

class RepoDisplay(object):
	def __init__(self, roots):
		self._shown_repos = {}
		self._unknown_repo = False
		repo_paths = set()
		for root_config in roots.values():
			portdir = root_config.settings.get("PORTDIR")
			if portdir:
				repo_paths.add(portdir)
			overlays = root_config.settings.get("PORTDIR_OVERLAY")
			if overlays:
				repo_paths.update(overlays.split())
		repo_paths = list(repo_paths)
		self._repo_paths = repo_paths
		self._repo_paths_real = [ os.path.realpath(repo_path) \
			for repo_path in repo_paths ]

		# pre-allocate index for PORTDIR so that it always has index 0.
		for root_config in roots.values():
			portdb = root_config.trees["porttree"].dbapi
			portdir = portdb.porttree_root
			if portdir:
				self.repoStr(portdir)

	def repoStr(self, repo_path_real):
		real_index = -1
		if repo_path_real:
			real_index = self._repo_paths_real.index(repo_path_real)
		if real_index == -1:
			s = "?"
			self._unknown_repo = True
		else:
			shown_repos = self._shown_repos
			repo_paths = self._repo_paths
			repo_path = repo_paths[real_index]
			index = shown_repos.get(repo_path)
			if index is None:
				index = len(shown_repos)
				shown_repos[repo_path] = index
			s = str(index)
		return s

	def __str__(self):
		"""
		In python-2.x, str() can trigger a UnicodeEncodeError here,
		so call __str__() directly.
		"""
		output = []
		shown_repos = self._shown_repos
		unknown_repo = self._unknown_repo
		if shown_repos or self._unknown_repo:
			output.append("Portage tree and overlays:\n")
		show_repo_paths = list(shown_repos)
		for repo_path, repo_index in shown_repos.items():
			show_repo_paths[repo_index] = repo_path
		if show_repo_paths:
			for index, repo_path in enumerate(show_repo_paths):
				output.append(" "+teal("["+str(index)+"]")+" %s\n" % repo_path)
		if unknown_repo:
			output.append(" "+teal("[?]") + \
				" indicates that the source repository could not be determined\n")
		return "".join(output)

