# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess

class EbuildSpawnProcess(AbstractEbuildProcess):
	"""
	Used by doebuild.spawn() to manage the spawned process.
	"""
	_spawn_kwarg_names = AbstractEbuildProcess._spawn_kwarg_names + \
		('fakeroot_state',)

	__slots__ = ('fakeroot_state', 'spawn_func')

	def _spawn(self, args, **kwargs):
		return self.spawn_func(args, env=self.settings.environ(), **kwargs)
