# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'features_set',
)

import logging

from portage.const import SUPPORTED_FEATURES
from portage.localization import _
from portage.output import colorize
from portage.util import writemsg_level

class features_set:
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

	def difference_update(self, values):
		self._settings.modifying()
		values = list(values)
		self._settings._features_overrides.extend('-' + k for k in values)
		remove_us = self._features.intersection(values)
		if remove_us:
			self._features.difference_update(values)
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

	def _validate(self):
		"""
		Implements unknown-features-warn and unknown-features-filter.
		"""
		if 'unknown-features-warn' in self._features:
			unknown_features = \
				self._features.difference(SUPPORTED_FEATURES)
			if unknown_features:
				unknown_features = unknown_features.difference(
					self._settings._unknown_features)
				if unknown_features:
					self._settings._unknown_features.update(unknown_features)
					writemsg_level(colorize("BAD",
						_("FEATURES variable contains unknown value(s): %s") % \
						", ".join(sorted(unknown_features))) \
						+ "\n", level=logging.WARNING, noiselevel=-1)

		if 'unknown-features-filter' in self._features:
			unknown_features = \
				self._features.difference(SUPPORTED_FEATURES)
			if unknown_features:
				self.difference_update(unknown_features)
				self._prune_overrides()

	def _prune_overrides(self):
		"""
		If there are lots of invalid package.env FEATURES settings
		then unknown-features-filter can make _features_overrides
		grow larger and larger, so prune it. This performs incremental
		stacking with preservation of negative values since they need
		to persist for future config.regenerate() calls.
		"""
		overrides_set = set(self._settings._features_overrides)
		positive = set()
		negative = set()
		for x in self._settings._features_overrides:
			if x[:1] == '-':
				positive.discard(x[1:])
				negative.add(x[1:])
			else:
				positive.add(x)
				negative.discard(x)
		self._settings._features_overrides[:] = \
			list(positive) + list('-' + x for x in negative)
