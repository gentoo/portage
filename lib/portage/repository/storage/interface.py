# Copyright 2018-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from portage.exception import PortageException


class RepoStorageException(PortageException):
	"""
	Base class for exceptions raise by RepoStorageInterface.
	"""


class RepoStorageInterface:
	"""
	Abstract repository storage interface.

	Implementations can assume that the repo.location directory already
	exists with appropriate permissions (SyncManager handles this).

	TODO: Add a method to check of a previous uncommitted update, which
	typically indicates a verification failure:
	    https://bugs.gentoo.org/662386
	"""
	def __init__(self, repo, spawn_kwargs):
		"""
		@param repo: repository configuration
		@type repo: portage.repository.config.RepoConfig
		@param spawn_kwargs: keyword arguments supported by the
			portage.process.spawn function
		@type spawn_kwargs: dict
		"""
		raise NotImplementedError

	async def init_update(self):
		"""
		Create an update directory as a destination to sync updates to.
		The directory will be populated with files from the previous
		immutable snapshot, if available. Note that this directory
		may contain hardlinks that reference files in the previous
		immutable snapshot, so these files should not be modified
		(tools like rsync and git normally break hardlinks when
		files need to be modified).

		@rtype: str
		@return: path of directory to update, populated with files from
			the previous snapshot if available
		"""
		raise NotImplementedError

	@property
	def current_update(self):
		"""
		Get the current update directory which would have been returned
		from the most recent call to the init_update method. This raises
		RepoStorageException if the init_update method has not been
		called.

		@rtype: str
		@return: path of directory to update
		"""
		raise NotImplementedError

	async def commit_update(self):
		"""
		Commit the current update directory, so that is becomes the
		latest immutable snapshot.
		"""
		raise NotImplementedError

	async def abort_update(self):
		"""
		Delete the current update directory. If there was not an update
		in progress, or it has already been committed, then this has
		no effect.
		"""
		raise NotImplementedError

	async def garbage_collection(self):
		"""
		Remove expired snapshots.
		"""
		raise NotImplementedError
