# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'features_set',
)

class features_set(object):
	"""
	Provides relevant set operations needed for access and modification of
	config.features. The FEATURES variable is automatically synchronized
	upon modification.

	Modifications result in a permanent override that will cause the change
	to propagate to the incremental stacking mechanism in config.regenerate().
	This eliminates the need to call config.backup_changes() when FEATURES
	is modified, since any overrides are guaranteed to persist despite calls
	to config.reset().
	"""

	def __init__(self, settings):
		self._settings = settings
		self._features = set()

	def __contains__(self, k):
		return k in self._features

	def __iter__(self):
		return iter(self._features)

	def _sync_env_var(self):
		self._settings['FEATURES'] = ' '.join(sorted(self._features))

	def add(self, k):
		self._settings.modifying()
		self._settings._features_overrides.append(k)
		if k not in self._features:
			self._features.add(k)
			self._sync_env_var()

	def update(self, values):
		self._settings.modifying()
		values = list(values)
		self._settings._features_overrides.extend(values)
		need_sync = False
		for k in values:
			if k in self._features:
				continue
			self._features.add(k)
			need_sync = True
		if need_sync:
			self._sync_env_var()

	def remove(self, k):
		"""
		This never raises KeyError, since it records a permanent override
		that will prevent the given flag from ever being added again by
		incremental stacking in config.regenerate().
		"""
		self.discard(k)

	def discard(self, k):
		self._settings.modifying()
		self._settings._features_overrides.append('-' + k)
		if k in self._features:
			self._features.remove(k)
			self._sync_env_var()
