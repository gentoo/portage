# Copyright 1999-2009 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

# for an explanation on this logic, see pym/_emerge/__init__.py
import os
import sys
if os.environ.__contains__("PORTAGE_PYTHONPATH"):
	sys.path.insert(0, os.environ["PORTAGE_PYTHONPATH"])
else:
	sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "pym"))
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
