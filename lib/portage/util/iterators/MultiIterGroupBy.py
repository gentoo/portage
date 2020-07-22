# Copyright 2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import bisect

class MultiIterGroupBy:
	"""
	This class functions similarly to the itertools.groupby function,
	except that it takes multiple source iterators as input. The source
	iterators must yield objects in sorted order. A group is yielded as
	soon as the progress of all iterators reaches a state which
	guarantees that there can not be any remaining (unseen) elements of
	the group. This is useful for incremental display of grouped search
	results.
	"""

	def __init__(self, iterators, key=None):
		self._iterators = iterators
		self._key = key

	def __iter__(self):

		trackers = []
		for iterator in self._iterators:
			trackers.append(_IteratorTracker(iterator))

		key_map = {}
		key_list = []
		eof = []
		key_getter = self._key
		if key_getter is None:
			key_getter = lambda x: x
		min_progress = None

		while trackers:

			for tracker in trackers:

				if tracker.current is not None and \
					tracker.current != min_progress:
					# The trackers are sorted by progress, so the
					# remaining trackers are guaranteed to have
					# sufficient progress.
					break

				# In order to avoid over-buffering (waste of memory),
				# only grab a single entry.
				try:
					entry = next(tracker.iterator)
				except StopIteration:
					eof.append(tracker)
				else:
					tracker.current = key_getter(entry)
					key_group = key_map.get(tracker.current)
					if key_group is None:
						key_group = []
						key_map[tracker.current] = key_group
						bisect.insort(key_list, tracker.current)
					key_group.append(entry)

			if eof:
				for tracker in eof:
					trackers.remove(tracker)
				del eof[:]

			if trackers:
				trackers.sort()
				min_progress = trackers[0].current
				# yield if key <= min_progress
				i = bisect.bisect_right(key_list, min_progress)
				yield_these = key_list[:i]
				del key_list[:i]
			else:
				yield_these = key_list
				key_list = []

			if yield_these:
				for k in yield_these:
					yield key_map.pop(k)

class _IteratorTracker:

	__slots__ = ('current', 'iterator')

	def __init__(self, iterator):

		self.iterator = iterator
		self.current = None

	def __lt__(self, other):
		if self.current is None:
			return other.current is not None
		return other.current is not None and \
			self.current < other.current
