#!/usr/bin/python
#
# Copyright(c) 2010, Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#


"""Provides a properties class to hold ebuild variables"""

from portage.api.settings import default_settings


class Properties(object):
	"""Contains all variables in an ebuild."""

	__slots__ = default_settings.keys + ["_dict", "__doc__", "__str__"]


	def __init__(self, _dict = None):
		self._dict = _dict

	def __getattr__(self, name):
		try: return self._dict[name]
		except: return ''

	def __str__(self):
		txt = []
		for k in self.__slots__[:-3]:
			txt.append( "	%s: %s" %(k, self.__getattr__(k)))
		return '\n'.join(txt)

	def keys(self):
		return self.__slots__[:-3]

	def get(self, name):
		return getattr(self, name)

	def get_slot(self):
		"""Return ebuild slot"""
		return self.slot

	def get_keywords(self):
		"""Returns a list of strings."""
		return self.keywords.split()

	def get_use_flags(self):
		"""Returns a list of strings."""
		return list(set(self.iuse.split()))

	def get_homepages(self):
		"""Returns a list of strings."""
		return self.homepage.split()
