# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.repository.storage.interface import (
	RepoStorageException,
	RepoStorageInterface,
)


class InplaceRepoStorage(RepoStorageInterface):
	"""
	Legacy repo storage behavior, where updates are applied in-place.
	This module is not recommended, since the repository is left in an
	unspecified (possibly malicious) state if the update fails.
	"""
	def __init__(self, repo, spawn_kwargs):
		self._user_location = repo.location
		self._update_location = None

	async def init_update(self):
		self._update_location = self._user_location
		return self._update_location

	@property
	def current_update(self):
		if self._update_location is None:
			raise RepoStorageException('current update does not exist')
		return self._update_location

	async def commit_update(self):
		self.current_update
		self._update_location = None

	async def abort_update(self):
		self._update_location = None

	async def garbage_collection(self):
		pass
