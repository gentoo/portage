# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
import portage
from portage import os

class EbuildSpawnProcess(AbstractEbuildProcess):
	"""
	Spawns misc-functions.sh with an existing ebuild environment.
	"""
	_spawn_kwarg_names = AbstractEbuildProcess._spawn_kwarg_names + \
		('fakeroot_state',)

	__slots__ = ('fakeroot_state', 'spawn_func')

	def _start(self):

		AbstractEbuildProcess._start(self)

	def _spawn(self, args, **kwargs):
		return self.spawn_func(args, **kwargs)
