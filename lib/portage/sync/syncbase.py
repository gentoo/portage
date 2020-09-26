# Copyright 2014-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

'''
Base class for performing sync operations.
This class contains common initialization code and functions.
'''

import functools
import logging
import os

import portage
from portage.repository.storage.interface import RepoStorageException
from portage.util import writemsg_level
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.backoff import RandomExponentialBackoff
from portage.util.futures._sync_decorator import _sync_methods
from portage.util.futures.retry import retry
from portage.util.futures.executor.fork import ForkExecutor
from . import _SUBMODULE_PATH_MAP

try:
	import gemato.openpgp
except ImportError:
	gemato = None


class SyncBase:
	'''Base Sync class for subclassing'''

	short_desc = "Perform sync operations on repositories"

	@staticmethod
	def name():
		return "BlankSync"


	def can_progressbar(self, func):
		return False


	def __init__(self, bin_command, bin_pkg):
		self.options = None
		self.settings = None
		self.logger = None
		self.repo = None
		self.xterm_titles = None
		self.spawn_kwargs = None
		self._repo_storage = None
		self._download_dir = None
		self.bin_command = None
		self._bin_command = bin_command
		self.bin_pkg = bin_pkg
		if bin_command:
			self.bin_command = portage.process.find_binary(bin_command)


	@property
	def has_bin(self):
		'''Checks for existance of the external binary, and also
		checks for storage driver configuration problems.

		MUST only be called after _kwargs() has set the logger
		'''
		if self.bin_command is None:
			msg = ["Command not found: %s" % self._bin_command,
			"Type \"emerge %s\" to enable %s support."
			% (self.bin_pkg, self._bin_command)]
			for l in msg:
				writemsg_level("!!! %s\n" % l,
					level=logging.ERROR, noiselevel=-1)
			return False

		try:
			self.repo_storage
		except RepoStorageException as e:
			writemsg_level("!!! %s\n" % (e,),
				level=logging.ERROR, noiselevel=-1)
			return False

		return True

	def _kwargs(self, kwargs):
		'''Sets internal variables from kwargs'''
		self.options = kwargs.get('options', {})
		self.settings = self.options.get('settings', None)
		self.logger = self.options.get('logger', None)
		self.repo = self.options.get('repo', None)
		self.xterm_titles = self.options.get('xterm_titles', False)
		self.spawn_kwargs = self.options.get('spawn_kwargs', None)

	def _select_storage_module(self):
		'''
		Select an appropriate implementation of RepoStorageInterface, based
		on repos.conf settings.

		@rtype: str
		@return: name of the selected repo storage constructor
		'''
		if self.repo.sync_rcu:
			mod_name = 'portage.repository.storage.hardlink_rcu.HardlinkRcuRepoStorage'
		elif self.repo.sync_allow_hardlinks:
			mod_name = 'portage.repository.storage.hardlink_quarantine.HardlinkQuarantineRepoStorage'
		else:
			mod_name = 'portage.repository.storage.inplace.InplaceRepoStorage'
		return mod_name

	@property
	def repo_storage(self):
		"""
		Get the repo storage driver instance. Raise RepoStorageException
		if there is a configuration problem
		"""
		if self._repo_storage is None:
			storage_cls = portage.load_mod(self._select_storage_module())
			self._repo_storage = _sync_methods(storage_cls(self.repo, self.spawn_kwargs), loop=global_event_loop())
		return self._repo_storage

	@property
	def download_dir(self):
		"""
		Get the path of the download directory, where the repository
		update is staged. The directory is initialized lazily, since
		the repository might already be at the latest revision, and
		there may be some cost associated with the directory
		initialization.
		"""
		if self._download_dir is None:
			self._download_dir = self.repo_storage.init_update()
		return self._download_dir

	def exists(self, **kwargs):
		'''Tests whether the repo actually exists'''
		if kwargs:
			self._kwargs(kwargs)
		elif not self.repo:
			return False
		if not os.path.exists(self.repo.location):
			return False
		return True


	def sync(self, **kwargs):
		'''Sync the repository'''
		raise NotImplementedError


	def post_sync(self, portdb, location, emerge_config):
		'''repo.sync_type == "Blank":
		# NOTE: Do this after reloading the config, in case
		# it did not exist prior to sync, so that the config
		# and portdb properly account for its existence.
		'''
		pass


	def _get_submodule_paths(self):
		paths = []
		emerge_config = self.options.get('emerge_config')
		if emerge_config is not None:
			for name in emerge_config.opts.get('--sync-submodule', []):
				paths.extend(_SUBMODULE_PATH_MAP[name])
		return tuple(paths)

	def retrieve_head(self, **kwargs):
		'''Get information about the head commit'''
		raise NotImplementedError

	def _key_refresh_retry_decorator(self):
		'''
		Return a retry decorator, or None if retry is disabled.

		If retry fails, the function reraises the exception raised
		by the decorated function. If retry times out and no exception
		is available to reraise, the function raises TimeoutError.
		'''
		errors = []

		if self.repo.sync_openpgp_key_refresh_retry_count is None:
			return None
		try:
			retry_count = int(self.repo.sync_openpgp_key_refresh_retry_count)
		except Exception as e:
			errors.append('sync-openpgp-key-refresh-retry-count: {}'.format(e))
		else:
			if retry_count <= 0:
				return None

		if self.repo.sync_openpgp_key_refresh_retry_overall_timeout is None:
			retry_overall_timeout = None
		else:
			try:
				retry_overall_timeout = float(self.repo.sync_openpgp_key_refresh_retry_overall_timeout)
			except Exception as e:
				errors.append('sync-openpgp-key-refresh-retry-overall-timeout: {}'.format(e))
			else:
				if retry_overall_timeout < 0:
					errors.append('sync-openpgp-key-refresh-retry-overall-timeout: '
						'value must be greater than or equal to zero: {}'.format(retry_overall_timeout))
				elif retry_overall_timeout == 0:
					retry_overall_timeout = None

		if self.repo.sync_openpgp_key_refresh_retry_delay_mult is None:
			retry_delay_mult = None
		else:
			try:
				retry_delay_mult = float(self.repo.sync_openpgp_key_refresh_retry_delay_mult)
			except Exception as e:
				errors.append('sync-openpgp-key-refresh-retry-delay-mult: {}'.format(e))
			else:
				if retry_delay_mult <= 0:
					errors.append('sync-openpgp-key-refresh-retry-mult: '
						'value must be greater than zero: {}'.format(retry_delay_mult))

		if self.repo.sync_openpgp_key_refresh_retry_delay_exp_base is None:
			retry_delay_exp_base = None
		else:
			try:
				retry_delay_exp_base = float(self.repo.sync_openpgp_key_refresh_retry_delay_exp_base)
			except Exception as e:
				errors.append('sync-openpgp-key-refresh-retry-delay-exp: {}'.format(e))
			else:
				if retry_delay_exp_base <= 0:
					errors.append('sync-openpgp-key-refresh-retry-delay-exp: '
						'value must be greater than zero: {}'.format(retry_delay_mult))

		if errors:
			lines = []
			lines.append('')
			lines.append('!!! Retry disabled for openpgp key refresh:')
			lines.append('')
			for msg in errors:
				lines.append('    {}'.format(msg))
			lines.append('')

			for line in lines:
				writemsg_level("{}\n".format(line),
					level=logging.ERROR, noiselevel=-1)

			return None

		return retry(
			reraise=True,
			try_max=retry_count,
			overall_timeout=(retry_overall_timeout if retry_overall_timeout > 0 else None),
			delay_func=RandomExponentialBackoff(
				multiplier=(1 if retry_delay_mult is None else retry_delay_mult),
				base=(2 if retry_delay_exp_base is None else retry_delay_exp_base)))

	def _refresh_keys(self, openpgp_env):
		"""
		Refresh keys stored in openpgp_env. Raises gemato.exceptions.GematoException
		or asyncio.TimeoutError on failure.

		@param openpgp_env: openpgp environment
		@type openpgp_env: gemato.openpgp.OpenPGPEnvironment
		"""
		out = portage.output.EOutput(quiet=('--quiet' in self.options['emerge_config'].opts))

		if not self.repo.sync_openpgp_key_refresh:
			out.ewarn('Key refresh is disabled via a repos.conf sync-openpgp-key-refresh')
			out.ewarn('setting, and this is a security vulnerability because it prevents')
			out.ewarn('detection of revoked keys!')
			return

		out.ebegin('Refreshing keys via WKD')
		if openpgp_env.refresh_keys_wkd():
			out.eend(0)
			return
		out.eend(1)

		out.ebegin('Refreshing keys from keyserver{}'.format(
			('' if self.repo.sync_openpgp_keyserver is None else ' ' + self.repo.sync_openpgp_keyserver)))
		retry_decorator = self._key_refresh_retry_decorator()
		if retry_decorator is None:
			openpgp_env.refresh_keys_keyserver(keyserver=self.repo.sync_openpgp_keyserver)
		else:
			def noisy_refresh_keys():
				"""
				Since retry does not help for some types of
				errors, display errors as soon as they occur.
				"""
				try:
					openpgp_env.refresh_keys_keyserver(keyserver=self.repo.sync_openpgp_keyserver)
				except Exception as e:
					writemsg_level("%s\n" % (e,),
						level=logging.ERROR, noiselevel=-1)
					raise # retry

			# The ThreadPoolExecutor that asyncio uses by default
			# does not support cancellation of tasks, therefore
			# use ForkExecutor for task cancellation support, in
			# order to enforce timeouts.
			loop = global_event_loop()
			with ForkExecutor(loop=loop) as executor:
				func_coroutine = functools.partial(loop.run_in_executor,
					executor, noisy_refresh_keys)
				decorated_func = retry_decorator(func_coroutine, loop=loop)
				loop.run_until_complete(decorated_func())
		out.eend(0)

	def _get_openpgp_env(self, openpgp_key_path=None):
		if gemato is not None:
			# Override global proxy setting with one provided in emerge configuration
			if 'http_proxy' in self.spawn_kwargs['env']:
				proxy = self.spawn_kwargs['env']['http_proxy']
			else:
				proxy = None

			if openpgp_key_path:
				openpgp_env = gemato.openpgp.OpenPGPEnvironment(proxy=proxy)
			else:
				openpgp_env = gemato.openpgp.OpenPGPSystemEnvironment(proxy=proxy)

			return openpgp_env


class NewBase(SyncBase):
	'''Subclasses Syncbase adding a new() and runs it
	instead of update() if the repository does not exist()'''


	def __init__(self, bin_command, bin_pkg):
		SyncBase.__init__(self, bin_command, bin_pkg)


	def sync(self, **kwargs):
		'''Sync the repository'''
		if kwargs:
			self._kwargs(kwargs)

		if not self.has_bin:
			return (1, False)

		if not self.exists():
			return self.new()
		return self.update()


	def new(self, **kwargs):
		'''Do the initial download and install of the repository'''
		raise NotImplementedError

	def update(self):
		'''Update existing repository
		'''
		raise NotImplementedError
