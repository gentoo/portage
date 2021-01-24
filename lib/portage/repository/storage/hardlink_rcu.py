# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import datetime

import portage
from portage import os
from portage.repository.storage.interface import (
	RepoStorageException,
	RepoStorageInterface,
)
from portage.util.futures import asyncio

from _emerge.SpawnProcess import SpawnProcess


class HardlinkRcuRepoStorage(RepoStorageInterface):
	"""
	Enable read-copy-update (RCU) behavior for sync operations. The
	current latest immutable version of a repository will be
	reference by a symlink found where the repository would normally
	be located.  Repository consumers should resolve the cannonical
	path of this symlink before attempt to access the repository,
	and all operations should be read-only, since the repository
	is considered immutable. Updates occur by atomic replacement
	of the symlink, which causes new consumers to use the new
	immutable version, while any earlier consumers continue to use
	the cannonical path that was resolved earlier.

	Performance is better than HardlinkQuarantineRepoStorage,
	since commit involves atomic replacement of a symlink. Since
	the symlink usage would require special handling for scenarios
	involving bind mounts and chroots, this module is not enabled
	by default.

	repos.conf parameters:

		sync-rcu-store-dir

			Directory path reserved for sync-rcu storage. This
			directory must have a unique value for each repository
			(do not set it in the DEFAULT section).  This directory
			must not contain any other files or directories aside
			from those that are created automatically when sync-rcu
			is enabled.

		sync-rcu-spare-snapshots = 1

			Number of spare snapshots for sync-rcu to retain with
			expired ttl. This protects the previous latest snapshot
			from being removed immediately after a new version
			becomes available, since it might still be used by
			running processes.

		sync-rcu-ttl-days = 7

			Number of days for sync-rcu to retain previous immutable
			snapshots of a repository. After the ttl of a particular
			snapshot has expired, it will be remove automatically (the
			latest snapshot is exempt, and sync-rcu-spare-snapshots
			configures the number of previous snapshots that are
			exempt). If the ttl is set too low, then a snapshot could
			expire while it is in use by a running process.

	"""
	def __init__(self, repo, spawn_kwargs):
		# Note that repo.location cannot substitute for repo.user_location here,
		# since we manage a symlink that resides at repo.user_location, and
		# repo.location is the irreversible result of realpath(repo.user_location).
		self._user_location = repo.user_location
		self._spawn_kwargs = spawn_kwargs

		if not repo.sync_allow_hardlinks:
			raise RepoStorageException("repos.conf sync-rcu setting"
				" for repo '%s' requires that sync-allow-hardlinks be enabled" % repo.name)

		# Raise an exception if repo.sync_rcu_store_dir is unset, since the
		# user needs to be aware of this location for bind mount and chroot
		# scenarios
		if not repo.sync_rcu_store_dir:
			raise RepoStorageException("repos.conf sync-rcu setting"
				" for repo '%s' requires that sync-rcu-store-dir be set" % repo.name)

		self._storage_location = repo.sync_rcu_store_dir
		if repo.sync_rcu_spare_snapshots is None or repo.sync_rcu_spare_snapshots < 0:
			self._spare_snapshots = 1
		else:
			self._spare_snapshots = repo.sync_rcu_spare_snapshots
		if self._spare_snapshots < 0:
			self._spare_snapshots = 0
		if repo.sync_rcu_ttl_days is None or repo.sync_rcu_ttl_days < 0:
			self._ttl_days = 1
		else:
			self._ttl_days = repo.sync_rcu_ttl_days
		self._update_location = None
		self._latest_symlink = os.path.join(self._storage_location, 'latest')
		self._latest_canonical = os.path.realpath(self._latest_symlink)
		if not os.path.exists(self._latest_canonical) or os.path.islink(self._latest_canonical):
			# It doesn't exist, or it's a broken symlink.
			self._latest_canonical = None
		self._snapshots_dir = os.path.join(self._storage_location, 'snapshots')

	async def _check_call(self, cmd, privileged=False):
		"""
		Run cmd and raise RepoStorageException on failure.

		@param cmd: command to executre
		@type cmd: list
		@param privileged: run with maximum privileges
		@type privileged: bool
		"""
		if privileged:
			kwargs = dict(fd_pipes=self._spawn_kwargs.get('fd_pipes'))
		else:
			kwargs = self._spawn_kwargs
		p = SpawnProcess(args=cmd, scheduler=asyncio.get_event_loop(), **kwargs)
		p.start()
		if await p.async_wait() != os.EX_OK:
			raise RepoStorageException('command exited with status {}: {}'.\
				format(p.returncode, ' '.join(cmd)))

	async def init_update(self):
		update_location = os.path.join(self._storage_location, 'update')
		await self._check_call(['rm', '-rf', update_location])

		# This assumes normal umask permissions if it doesn't exist yet.
		portage.util.ensure_dirs(self._storage_location)

		if self._latest_canonical is not None:
			portage.util.ensure_dirs(update_location)
			portage.util.apply_stat_permissions(update_location,
				os.stat(self._user_location))
			# Use  rsync --link-dest to hardlink a files into update_location,
			# since cp -l is not portable.
			await self._check_call(['rsync', '-a', '--link-dest', self._latest_canonical,
				self._latest_canonical + '/', update_location + '/'])

		elif not os.path.islink(self._user_location):
			await self._migrate(update_location)
			update_location = await self.init_update()

		self._update_location = update_location

		return self._update_location

	async def _migrate(self, update_location):
		"""
		When repo.user_location is a normal directory, migrate it to
		storage so that it can be replaced with a symlink. After migration,
		commit the content as the latest snapshot.
		"""
		try:
			os.rename(self._user_location, update_location)
		except OSError:
			portage.util.ensure_dirs(update_location)
			portage.util.apply_stat_permissions(update_location,
				os.stat(self._user_location))
			# It's probably on a different device, so copy it.
			await self._check_call(['rsync', '-a',
				self._user_location + '/', update_location + '/'])

			# Remove the old copy so that symlink can be created. Run with
			# maximum privileges, since removal requires write access to
			# the parent directory.
			await self._check_call(['rm', '-rf', self._user_location], privileged=True)

		self._update_location = update_location

		# Make this copy the latest snapshot
		await self.commit_update()

	@property
	def current_update(self):
		if self._update_location is None:
			raise RepoStorageException('current update does not exist')
		return self._update_location

	async def commit_update(self):
		update_location = self.current_update
		self._update_location = None
		try:
			snapshots = [int(name) for name in os.listdir(self._snapshots_dir)]
		except OSError:
			snapshots = []
			portage.util.ensure_dirs(self._snapshots_dir)
			portage.util.apply_stat_permissions(self._snapshots_dir,
				os.stat(self._storage_location))
		if snapshots:
			new_id = max(snapshots) + 1
		else:
			new_id = 1
		os.rename(update_location, os.path.join(self._snapshots_dir, str(new_id)))
		new_symlink = self._latest_symlink + '.new'
		try:
			os.unlink(new_symlink)
		except OSError:
			pass
		os.symlink('snapshots/{}'.format(new_id), new_symlink)

		# If SyncManager.pre_sync creates an empty directory where
		# self._latest_symlink is suppose to be (which is normal if
		# sync-rcu-store-dir has been removed), then we need to remove
		# the directory or else rename will raise IsADirectoryError
		# when we try to replace the directory with a symlink.
		try:
			os.rmdir(self._latest_symlink)
		except OSError:
			pass

		os.rename(new_symlink, self._latest_symlink)

		try:
			user_location_correct = os.path.samefile(self._user_location, self._latest_symlink)
		except OSError:
			user_location_correct = False

		if not user_location_correct:
			new_symlink = self._user_location + '.new'
			try:
				os.unlink(new_symlink)
			except OSError:
				pass
			os.symlink(self._latest_symlink, new_symlink)
			os.rename(new_symlink, self._user_location)

	async def abort_update(self):
		if self._update_location is not None:
			update_location = self._update_location
			self._update_location = None
			await self._check_call(['rm', '-rf', update_location])

	async def garbage_collection(self):
		snap_ttl = datetime.timedelta(days=self._ttl_days)
		snapshots = sorted(int(name) for name in os.listdir(self._snapshots_dir))
		# always preserve the latest snapshot
		protect_count = self._spare_snapshots + 1
		while snapshots and protect_count:
			protect_count -= 1
			snapshots.pop()
		for snap_id in snapshots:
			snap_path = os.path.join(self._snapshots_dir, str(snap_id))
			try:
				st = os.stat(snap_path)
			except OSError:
				continue
			snap_timestamp = datetime.datetime.utcfromtimestamp(st.st_mtime)
			if (datetime.datetime.utcnow() - snap_timestamp) < snap_ttl:
				continue
			await self._check_call(['rm', '-rf', snap_path])
