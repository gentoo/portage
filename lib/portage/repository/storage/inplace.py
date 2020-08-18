# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from portage.repository.storage.interface import (
	RepoStorageException,
	RepoStorageInterface,
)
from portage.util.futures.compat_coroutine import coroutine, coroutine_return


class InplaceRepoStorage(RepoStorageInterface):
	"""
	Legacy repo storage behavior, where updates are applied in-place.
	This module is not recommended, since the repository is left in an
	unspecified (possibly malicious) state if the update fails.
	"""
	def __init__(self, repo, spawn_kwargs):
		self._user_location = repo.location
		self._update_location = None

	@coroutine
	def init_update(self, loop=None):
		self._update_location = self._user_location
		coroutine_return(self._update_location)
		yield None

	@property
	def current_update(self, loop=None):
		if self._update_location is None:
			raise RepoStorageException('current update does not exist')
		return self._update_location

	@coroutine
	def commit_update(self, loop=None):
		self.current_update
		self._update_location = None
		coroutine_return()
		yield None

	@coroutine
	def abort_update(self, loop=None):
		self._update_location = None
		coroutine_return()
		yield None

	@coroutine
	def garbage_collection(self, loop=None):
		coroutine_return()
		yield None
