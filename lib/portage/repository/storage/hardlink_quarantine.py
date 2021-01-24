# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage import os
from portage.repository.storage.interface import (
	RepoStorageException,
	RepoStorageInterface,
)
from portage.util.futures import asyncio

from _emerge.SpawnProcess import SpawnProcess


class HardlinkQuarantineRepoStorage(RepoStorageInterface):
	"""
	This is the default storage module, since its quite compatible with
	most configurations.

	It's desirable to be able to create shared hardlinks between the
	download directory and the normal repository, and this is facilitated
	by making the download directory be a subdirectory of the normal
	repository location (ensuring that no mountpoints are crossed).
	Shared hardlinks are created by using the rsync --link-dest option.

	Since the download is initially unverified, it is safest to save
	it in a quarantine directory. The quarantine directory is also
	useful for making the repository update more atomic, so that it
	less likely that normal repository location will be observed in
	a partially synced state.
	"""
	def __init__(self, repo, spawn_kwargs):
		self._user_location = repo.location
		self._update_location = None
		self._spawn_kwargs = spawn_kwargs
		self._current_update = None

	async def _check_call(self, cmd):
		"""
		Run cmd and raise RepoStorageException on failure.

		@param cmd: command to executre
		@type cmd: list
		"""
		p = SpawnProcess(args=cmd, scheduler=asyncio.get_event_loop(), **self._spawn_kwargs)
		p.start()
		if await p.async_wait() != os.EX_OK:
			raise RepoStorageException('command exited with status {}: {}'.\
				format(p.returncode, ' '.join(cmd)))

	async def init_update(self):
		update_location = os.path.join(self._user_location, '.tmp-unverified-download-quarantine')
		await self._check_call(['rm', '-rf', update_location])

		# Use  rsync --link-dest to hardlink a files into self._update_location,
		# since cp -l is not portable.
		await self._check_call(['rsync', '-a', '--link-dest', self._user_location,
			'--exclude=/distfiles', '--exclude=/local', '--exclude=/lost+found', '--exclude=/packages',
			'--exclude', '/{}'.format(os.path.basename(update_location)),
			self._user_location + '/', update_location + '/'])

		self._update_location = update_location

		return self._update_location

	@property
	def current_update(self):
		if self._update_location is None:
			raise RepoStorageException('current update does not exist')
		return self._update_location

	async def commit_update(self):
		update_location = self.current_update
		self._update_location = None
		await self._check_call(['rsync', '-a', '--delete',
			'--exclude=/distfiles', '--exclude=/local', '--exclude=/lost+found', '--exclude=/packages',
			'--exclude', '/{}'.format(os.path.basename(update_location)),
			update_location + '/', self._user_location + '/'])

		await self._check_call(['rm', '-rf', update_location])

	async def abort_update(self):
		if self._update_location is not None:
			update_location = self._update_location
			self._update_location = None
			await self._check_call(['rm', '-rf', update_location])

	async def garbage_collection(self):
		await self.abort_update()
