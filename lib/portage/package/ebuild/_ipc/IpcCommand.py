# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

class IpcCommand:

	__slots__ = ()

	def __call__(self, argv):
		raise NotImplementedError(self)
