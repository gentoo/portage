# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

import copy
if not hasattr(__builtins__, "set"):
	from sets import Set as set
from cache import template

class database(template.database):

	autocommits = True
	serialize_eclasses = False

	def __init__(self, *args, **config):
		config.pop("gid", None)
		super(database, self).__init__(*args, **config)
		self._data = {}
		self.iterkeys = self._data.iterkeys
		self._delitem = self._data.__delitem__
		self.__contains__ = self._data.__contains__

	def _setitem(self, name, values):
		self._data[name] = copy.deepcopy(values)

	def _getitem(self, cpv):
		return copy.deepcopy(self._data[cpv])
