# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import portage

class UninstallFailure(portage.exception.PortageException):
	"""
	An instance of this class is raised by unmerge() when
	an uninstallation fails.
	"""
	status = 1
	def __init__(self, *pargs):
		portage.exception.PortageException.__init__(self, pargs)
		if pargs:
			self.status = pargs[0]
