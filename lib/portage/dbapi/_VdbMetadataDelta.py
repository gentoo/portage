# Copyright 2014-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import io
import json
import os

from portage import _encodings
from portage.util import atomic_ofstream
from portage.versions import cpv_getkey

class VdbMetadataDelta:

	_format_version  = "1"

	def __init__(self, vardb):
		self._vardb = vardb

	def initialize(self, timestamp):
		with atomic_ofstream(self._vardb._cache_delta_filename, 'w',
			encoding=_encodings['repo.content'], errors='strict') as f:
			json.dump({
				"version": self._format_version,
				"timestamp": timestamp
			}, f, ensure_ascii=False)

	def load(self):

		if not os.path.exists(self._vardb._aux_cache_filename):
			# If the primary cache doesn't exist yet, then
			# we can't record a delta against it.
			return None

		try:
			with io.open(self._vardb._cache_delta_filename, 'r',
				encoding=_encodings['repo.content'],
				errors='strict') as f:
				cache_obj = json.load(f)
		except EnvironmentError as e:
			if e.errno not in (errno.ENOENT, errno.ESTALE):
				raise
		except (SystemExit, KeyboardInterrupt):
			raise
		except Exception:
			# Corrupt, or not json format.
			pass
		else:
			try:
				version = cache_obj["version"]
			except KeyError:
				pass
			else:
				# Verify that the format version is compatible,
				# since a newer version of portage may have
				# written an incompatible file.
				if version == self._format_version:
					try:
						deltas = cache_obj["deltas"]
					except KeyError:
						cache_obj["deltas"] = deltas = []

					if isinstance(deltas, list):
						return cache_obj

		return None

	def loadRace(self):
		"""
		This calls self.load() and validates the timestamp
		against the currently loaded self._vardb._aux_cache. If a
		concurrent update causes the timestamps to be inconsistent,
		then it reloads the caches and tries one more time before
		it aborts. In practice, the race is very unlikely, so
		this will usually succeed on the first try.
		"""

		tries = 2
		while tries:
			tries -= 1
			cache_delta = self.load()
			if cache_delta is not None and \
				cache_delta.get("timestamp") != \
				self._vardb._aux_cache.get("timestamp", False):
				self._vardb._aux_cache_obj = None
			else:
				return cache_delta

		return None

	def recordEvent(self, event, cpv, slot, counter):

		self._vardb.lock()
		try:
			deltas_obj = self.load()

			if deltas_obj is None:
				# We can't record meaningful deltas without
				# a pre-existing state.
				return

			delta_node = {
				"event": event,
				"package": cpv.cp,
				"version": cpv.version,
				"slot": slot,
				"counter": "%s" % counter
			}

			deltas_obj["deltas"].append(delta_node)

			# Eliminate earlier nodes cancelled out by later nodes
			# that have identical package and slot attributes.
			filtered_list = []
			slot_keys = set()
			version_keys = set()
			for delta_node in reversed(deltas_obj["deltas"]):
				slot_key = (delta_node["package"],
					delta_node["slot"])
				version_key = (delta_node["package"],
					delta_node["version"])
				if not (slot_key in slot_keys or \
					version_key in version_keys):
					filtered_list.append(delta_node)
					slot_keys.add(slot_key)
					version_keys.add(version_key)

			filtered_list.reverse()
			deltas_obj["deltas"] = filtered_list

			f = atomic_ofstream(self._vardb._cache_delta_filename,
				mode='w', encoding=_encodings['repo.content'])
			json.dump(deltas_obj, f, ensure_ascii=False)
			f.close()

		finally:
			self._vardb.unlock()

	def applyDelta(self, data):
		packages = self._vardb._aux_cache["packages"]
		deltas = {}
		for delta in data["deltas"]:
			cpv = delta["package"] + "-" + delta["version"]
			deltas[cpv] = delta
			event = delta["event"]
			if event == "add":
				# Use aux_get to populate the cache
				# for this cpv.
				if cpv not in packages:
					try:
						self._vardb.aux_get(cpv, ["DESCRIPTION"])
					except KeyError:
						pass
			elif event == "remove":
				packages.pop(cpv, None)

		if deltas:
			# Delete removed or replaced versions from affected slots
			for cached_cpv, (mtime, metadata) in list(packages.items()):
				if cached_cpv in deltas:
					continue

				removed = False
				for cpv, delta in deltas.items():
					if (cached_cpv.startswith(delta["package"]) and
						metadata.get("SLOT") == delta["slot"] and
						cpv_getkey(cached_cpv) == delta["package"]):
						removed = True
						break

				if removed:
					del packages[cached_cpv]
					del deltas[cpv]
					if not deltas:
						break
