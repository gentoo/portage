# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.dep import _repo_separator
from portage.exception import InvalidDependString
from portage.localization import _
from portage.util._async.AsyncScheduler import AsyncScheduler
from .ManifestTask import ManifestTask

class ManifestScheduler(AsyncScheduler):

	def __init__(self, portdb, cp_iter=None,
		gpg_cmd=None, gpg_vars=None, force_sign_key=None, **kwargs):

		AsyncScheduler.__init__(self, **kwargs)

		self._portdb = portdb

		if cp_iter is None:
			cp_iter = self._iter_every_cp()
		self._cp_iter = cp_iter
		self._gpg_cmd = gpg_cmd
		self._gpg_vars = gpg_vars
		self._force_sign_key = force_sign_key
		self._task_iter = self._iter_tasks()

	def _next_task(self):
		return next(self._task_iter)

	def _iter_every_cp(self):
		every_cp = self._portdb.cp_all()
		every_cp.sort(reverse=True)
		try:
			while not self._terminated_tasks:
				yield every_cp.pop()
		except IndexError:
			pass

	def _iter_tasks(self):
		portdb = self._portdb
		distdir = portdb.settings["DISTDIR"]
		disabled_repos = set()

		for cp in self._cp_iter:
			if self._terminated_tasks:
				break
			# We iterate over portdb.porttrees, since it's common to
			# tweak this attribute in order to adjust repo selection.
			for mytree in portdb.porttrees:
				repo_config = portdb.repositories.get_repo_for_location(mytree)
				if not repo_config.create_manifest:
					if repo_config.name not in disabled_repos:
						disabled_repos.add(repo_config.name)
						portage.writemsg(
							_(">>> Skipping creating Manifest for %s%s%s; "
							"repository is configured to not use them\n") %
							(cp, _repo_separator, repo_config.name),
							noiselevel=-1)
					continue
				cpv_list = portdb.cp_list(cp, mytree=[repo_config.location])
				if not cpv_list:
					continue
				fetchlist_dict = {}
				try:
					for cpv in cpv_list:
						fetchlist_dict[cpv] = \
							list(portdb.getFetchMap(cpv, mytree=mytree))
				except InvalidDependString as e:
					portage.writemsg(
						_("!!! %s%s%s: SRC_URI: %s\n") %
						(cp, _repo_separator, repo_config.name, e),
						noiselevel=-1)
					self._error_count += 1
					continue

				yield ManifestTask(cp=cp, distdir=distdir,
					fetchlist_dict=fetchlist_dict, repo_config=repo_config,
					gpg_cmd=self._gpg_cmd, gpg_vars=self._gpg_vars,
					force_sign_key=self._force_sign_key)

	def _task_exit(self, task):

		if task.returncode != os.EX_OK:
			if not self._terminated_tasks:
				portage.writemsg(
					"Error processing %s%s%s, continuing...\n" %
					(task.cp, _repo_separator, task.repo_config.name),
					noiselevel=-1)

		AsyncScheduler._task_exit(self, task)
