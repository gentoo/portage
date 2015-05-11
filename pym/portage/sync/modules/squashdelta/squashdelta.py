#	vim:fileencoding=utf-8:noet
# (c) 2015 Michał Górny <mgorny@gentoo.org>
# Distributed under the terms of the GNU General Public License v2

'''SquashDelta sync module for portage'''


import errno
import io
import logging
import os
import os.path
import re

import portage
from portage.package.ebuild.fetch import fetch
from portage.sync.syncbase import SyncBase

from . import DEFAULT_CACHE_LOCATION


class SquashDeltaError(Exception):
	pass


class SquashDeltaSync(SyncBase):
	'''Repository syncing using SquashFS deltas'''

	short_desc = "Repository syncing using SquashFS deltas"

	@staticmethod
	def name():
		return "SquashDeltaSync"

	def __init__(self):
		super(SquashDeltaSync, self).__init__(
				'squashmerge', 'dev-util/squashmerge')
		self.repo_re = re.compile(self.repo.name + '-(.*)$')

	def _configure(self):
		self.my_settings = portage.config(clone = self.settings)
		self.cache_location = DEFAULT_CACHE_LOCATION

		# override fetching location
		self.my_settings['DISTDIR'] = self.cache_location

		# make sure we append paths correctly
		self.base_uri = self.repo.sync_uri
		if not self.base_uri.endswith('/'):
			self.base_uri += '/'

	def _fetch(self, fn, **kwargs):
		# disable implicit mirrors support since it relies on file
		# being in distfiles/
		kwargs['try_mirrors'] = 0
		if not fetch([self.base_uri + fn], self.my_settings, **kwargs):
			raise SquashDeltaError()

	def _openpgp_verify(self, data):
		if 'webrsync-gpg' in self.my_settings.features:
			# TODO: OpenPGP signature verification
			# raise SquashDeltaError if it fails
			pass

	def _parse_sha512sum(self, path):
		# sha512sum.txt parsing
		with io.open(path, 'r', encoding='utf8') as f:
			data = f.readlines()

		if not self._openpgp_verify(data):
			logging.error('OpenPGP verification failed for sha512sum.txt')
			raise SquashDeltaError()

		# current tag
		current_re = re.compile('current:', re.IGNORECASE)
		# checksum
		checksum_re = re.compile('^([a-f0-9]{128})\s+(.*)$', re.IGNORECASE)

		def iter_snapshots(lines):
			for l in lines:
				m = current_re.search(l)
				if m:
					for s in l[m.end():].split():
						yield s

		def iter_checksums(lines):
			for l in lines:
				m = checksum_re.match(l)
				if m:
					yield (m.group(2), {
						'size': None,
						'SHA512': m.group(1),
					})

		return (iter_snapshots(data), dict(iter_checksums(data)))

	def _find_newest_snapshot(self, snapshots):
		# look for current indicator
		for s in snapshots:
			m = self.repo_re.match(s)
			if m:
				new_snapshot = m.group(0) + '.sqfs'
				new_version = m.group(1)
				break
		else:
			logging.error('Unable to find current snapshot in sha512sum.txt')
			raise SquashDeltaError()

		new_path = os.path.join(self.cache_location, new_snapshot)
		return (new_snapshot, new_version, new_path)

	def _find_local_snapshot(self, current_path):
		# try to find a local snapshot
		try:
			old_snapshot = os.readlink(current_path)
		except OSError:
			return ('', '', '')
		else:
			m = self.repo_re.match(old_snapshot)
			if m and old_snapshot.endswith('.sqfs'):
				old_version = m.group(1)[:-5]
				old_path = os.path.join(self.cache_location, old_snapshot)

		return (old_snapshot, old_version, old_path)

	def _try_delta(self, old_version, new_version, old_path, new_path, my_digests):
		# attempt to update
		delta_path = None
		expected_delta = '%s-%s-%s.sqdelta' % (
				self.repo.name, old_version, new_version)
		if expected_delta not in my_digests:
			logging.warning('No delta for %s->%s, fetching new snapshot.'
					% (old_version, new_version))
		else:
			delta_path = os.path.join(self.cache_location, expected_delta)

			if not self._fetch(expected_delta, digests = my_digests):
				raise SquashDeltaError()
			if not self.has_bin:
				raise SquashDeltaError()

			ret = portage.process.spawn([self.bin_command,
					old_path, delta_path, new_path], **self.spawn_kwargs)
			if ret != os.EX_OK:
				logging.error('Merging the delta failed')
				raise SquashDeltaError()
		return delta_path

	def _update_symlink(self, new_snapshot, current_path):
		# using external ln for two reasons:
		# 1. clean --force (unlike python's unlink+symlink)
		# 2. easy userpriv (otherwise we'd have to lchown())
		ret = portage.process.spawn(['ln', '-s', '-f', new_snapshot, current_path],
				**self.spawn_kwargs)
		if ret != os.EX_OK:
			logging.error('Unable to set -current symlink')
			raise SquashDeltaError()

	def _cleanup(self, path):
		try:
			os.unlink(path)
		except OSError as e:
			logging.warning('Unable to clean up ' + path + ': ' + str(e))

	def _update_mount(self, current_path):
		mount_cmd = ['mount', current_path, self.repo.location]
		can_mount = True
		if os.path.ismount(self.repo.location):
			# need to umount old snapshot
			ret = portage.process.spawn(['umount', '-l', self.repo.location])
			if ret != os.EX_OK:
				logging.error('Unable to unmount old SquashFS after update')
				raise SquashDeltaError()
		else:
			try:
				os.makedirs(self.repo.location)
			except OSError as e:
				if e.errno != errno.EEXIST:
					raise

		ret = portage.process.spawn(mount_cmd)
		if ret != os.EX_OK:
			logging.error('Unable to (re-)mount SquashFS after update')
			raise SquashDeltaError()

	def sync(self, **kwargs):
		'''Sync the repository'''
		self._kwargs(kwargs)

		try:
			self._configure()

			# fetch sha512sum.txt
			sha512_path = os.path.join(self.cache_location, 'sha512sum.txt')
			try:
				os.unlink(sha512_path)
			except OSError as e:
				if e.errno != errno.ENOENT:
					logging.error('Unable to unlink sha512sum.txt')
					return (1, False)
			self._fetch('sha512sum.txt')

			snapshots, my_digests = self._parse_sha512sum(sha512_path)

			current_path = os.path.join(self.cache_location,
					self.repo.name + '-current.sqfs')
			new_snapshot, new_version, new_path = (
					self._find_newest_snapshot(snapshots))
			old_snapshot, old_version, old_path = (
					self._find_local_snapshot(current_path))

			if old_version:
				if old_version == new_version:
					logging.info('Snapshot up-to-date, verifying integrity.')
				else:
					delta_path = self._try_delta(old_version, new_version,
							old_path, new_path, my_digests)
					# pass-through to verification and cleanup

			# fetch full snapshot or verify the one we have
			self._fetch(new_snapshot, digests = my_digests)

			# create/update -current symlink
			self._update_symlink(new_snapshot, current_path)

			# remove old snapshot
			if old_version is not None and old_version != new_version:
				self._cleanup(old_path)
				if delta_path is not None:
					self._cleanup(delta_path)
			self._cleanup(sha512_path)

			self._update_mount(current_path)

			return (0, True)
		except SquashDeltaError:
			return (1, False)
