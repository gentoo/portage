# Copyright 2010-2013 Gentoo Foundation
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

		env = self.settings.environ()

		if self._dummy_pipe_fd is not None:
			env["PORTAGE_PIPE_FD"] = str(self._dummy_pipe_fd)

		return self.spawn_func(args, env=env, **kwargs)
