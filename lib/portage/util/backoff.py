# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'ExponentialBackoff',
	'RandomExponentialBackoff',
)

import random
import sys


class ExponentialBackoff:
	"""
	An object that when called with number of previous tries, calculates
	an exponential delay for the next try.
	"""
	def __init__(self, multiplier=1, base=2, limit=sys.maxsize):
		"""
		@param multiplier: constant multiplier
		@type multiplier: int or float
		@param base: maximum number of tries
		@type base: int or float
		@param limit: maximum number of seconds to delay
		@type limit: int or float
		"""
		self._multiplier = multiplier
		self._base = base
		self._limit = limit

	def __call__(self, tries):
		"""
		Given a number of previous tries, calculate the amount of time
		to delay the next try.

		@param tries: number of previous tries
		@type tries: int
		@return: amount of time to delay the next try
		@rtype: int
		"""
		try:
			return min(self._limit, self._multiplier * (self._base ** tries))
		except OverflowError:
			return self._limit


class RandomExponentialBackoff(ExponentialBackoff):
	"""
	Equivalent to ExponentialBackoff, with an extra multiplier that uses
	a random distribution between 0 and 1.
	"""
	def __call__(self, tries):
		return random.random() * super(RandomExponentialBackoff, self).__call__(tries)
