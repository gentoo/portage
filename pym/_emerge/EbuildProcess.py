# Copyright 1999-2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractEbuildProcess import AbstractEbuildProcess
import portage
portage.proxy.lazyimport.lazyimport(globals(),
	'portage.package.ebuild.doebuild:_doebuild_spawn,_spawn_actionmap'
)

class EbuildProcess(AbstractEbuildProcess):

	__slots__ = ('actionmap',)

	def _spawn(self, args, **kwargs):

		actionmap = self.actionmap
		if actionmap is None:
			actionmap = _spawn_actionmap(self.settings)

		return _doebuild_spawn(self.phase, self.settings,
				actionmap=actionmap, **kwargs)
