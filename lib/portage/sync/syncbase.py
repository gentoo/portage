# Copyright 2014-2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

'''
Base class for performing sync operations.
This class contains common initialization code and functions.
'''

from __future__ import unicode_literals
import functools
import logging
import os

import portage
from portage.util import writemsg_level
from portage.util._eventloop.global_event_loop import global_event_loop
from portage.util.backoff import RandomExponentialBackoff
from portage.util.futures.retry import retry
from portage.util.futures.executor.fork import ForkExecutor
from . import _SUBMODULE_PATH_MAP

class SyncBase(object):
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
		self.bin_command = None
		self._bin_command = bin_command
		self.bin_pkg = bin_pkg
		if bin_command:
			self.bin_command = portage.process.find_binary(bin_command)


	@property
	def has_bin(self):
		'''Checks for existance of the external binary.

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
		return True


	def _kwargs(self, kwargs):
		'''Sets internal variables from kwargs'''
		self.options = kwargs.get('options', {})
		self.settings = self.options.get('settings', None)
		self.logger = self.options.get('logger', None)
		self.repo = self.options.get('repo', None)
		self.xterm_titles = self.options.get('xterm_titles', False)
		self.spawn_kwargs = self.options.get('spawn_kwargs', None)


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
		out.ebegin('Refreshing keys from keyserver')
		retry_decorator = self._key_refresh_retry_decorator()
		if retry_decorator is None:
			openpgp_env.refresh_keys()
		else:
			def noisy_refresh_keys():
				"""
				Since retry does not help for some types of
				errors, display errors as soon as they occur.
				"""
				try:
					openpgp_env.refresh_keys()
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
