# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
import portage
from portage import os
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.doebuild:_doebuild_exit_status_check_and_log'
)

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

	def _set_returncode(self, wait_retval):
		AbstractEbuildProcess._set_returncode(self, wait_retval)
		phase = self.settings.get("EBUILD_PHASE")
		if not phase:
			phase = 'other'
		self.returncode = _doebuild_exit_status_check_and_log(
			self.settings, phase, self.returncode)
