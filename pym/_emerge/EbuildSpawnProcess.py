# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
import portage
from portage import os

class EbuildSpawnProcess(AbstractEbuildProcess):
	"""
	Used by doebuild.spawn() to manage the spawned process.
	"""

	__slots__ = ('spawn_func',)

	def _spawn(self, args, **kwargs):
		return self.spawn_func(args, env=self.settings.environ(), **kwargs)
