# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import unicode_literals

import fnmatch
from itertools import chain
import os
import re

from portage.util import shlex_split

class SonameDepsProcessor(object):
	"""
	Processes NEEDED.ELF.2 entries for one package, in order to generate
	REQUIRES and PROVIDES metadata.

	Any sonames provided by the package will automatically be filtered
	from the generated REQUIRES values.
	"""

	def __init__(self, provides_exclude, requires_exclude):
		"""
		@param provides_exclude: PROVIDES_EXCLUDE value
		@type provides_exclude: str
		@param requires_exclude: REQUIRES_EXCLUDE value
		@type requires_exclude: str
		"""
		self._provides_exclude = self._exclude_pattern(provides_exclude)
		self._requires_exclude = self._exclude_pattern(requires_exclude)
		self._requires_map = {}
		self._provides_map = {}
		self._provides_unfiltered = {}
		self._provides = None
		self._requires = None
		self._intersected = False

	@staticmethod
	def _exclude_pattern(s):
		# shlex_split enables quoted whitespace inside patterns
		if s:
			pat = re.compile("|".join(
				fnmatch.translate(x.lstrip(os.sep))
				for x in shlex_split(s)))
		else:
			pat = None
		return pat

	def add(self, entry):
		"""
		Add one NEEDED.ELF.2 entry, for inclusion in the generated
		REQUIRES and PROVIDES values.

		@param entry: NEEDED.ELF.2 entry
		@type entry: NeededEntry
		"""

		multilib_cat = entry.multilib_category
		if multilib_cat is None:
			# This usage is invalid. The caller must ensure that
			# the multilib category data is supplied here.
			raise AssertionError(
				"Missing multilib category data: %s" % entry.filename)

		if entry.needed and (
			self._requires_exclude is None or
			self._requires_exclude.match(
			entry.filename.lstrip(os.sep)) is None):
			for x in entry.needed:
				if (self._requires_exclude is None or
					self._requires_exclude.match(x) is None):
					self._requires_map.setdefault(
						multilib_cat, set()).add(x)

		if entry.soname:
			self._provides_unfiltered.setdefault(
				multilib_cat, set()).add(entry.soname)

		if entry.soname and (
			self._provides_exclude is None or
			(self._provides_exclude.match(
			entry.filename.lstrip(os.sep)) is None and
			self._provides_exclude.match(entry.soname) is None)):
			self._provides_map.setdefault(
				multilib_cat, set()).add(entry.soname)

	def _intersect(self):
		requires_map = self._requires_map
		provides_map = self._provides_map
		provides_unfiltered = self._provides_unfiltered

		for multilib_cat in set(chain(requires_map, provides_map)):
			requires_map.setdefault(multilib_cat, set())
			provides_map.setdefault(multilib_cat, set())
			provides_unfiltered.setdefault(multilib_cat, set())
			for soname in list(requires_map[multilib_cat]):
				if soname in provides_unfiltered[multilib_cat]:
					requires_map[multilib_cat].remove(soname)

		provides_data = []
		for multilib_cat in sorted(provides_map):
			if provides_map[multilib_cat]:
				provides_data.append(multilib_cat + ":")
				provides_data.extend(sorted(provides_map[multilib_cat]))

		if provides_data:
			self._provides = " ".join(provides_data) + "\n"

		requires_data = []
		for multilib_cat in sorted(requires_map):
			if requires_map[multilib_cat]:
				requires_data.append(multilib_cat + ":")
				requires_data.extend(sorted(requires_map[multilib_cat]))

		if requires_data:
			self._requires = " ".join(requires_data) + "\n"

		self._intersected = True

	@property
	def provides(self):
		"""
		@rtype: str
		@return: PROVIDES value generated from NEEDED.ELF.2 entries
		"""
		if not self._intersected:
			self._intersect()
		return self._provides

	@property
	def requires(self):
		"""
		@rtype: str
		@return: REQUIRES value generated from NEEDED.ELF.2 entries
		"""
		if not self._intersected:
			self._intersect()
		return self._requires
