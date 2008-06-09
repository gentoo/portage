# Copyright: 2005-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

# all vars that are to wind up in portage_const must have their name listed in __all__

__all__ = ["EAPIPREFIX", "EPREFIX", "SYSCONFDIR", "DATADIR", "PORTAGE_BASE",
		"portageuser", "portagegroup", "rootuser", "rootuid", "rootgid"]

from os import path

EAPIPREFIX   = @EAPIPREFIX@
EPREFIX      = @PORTAGE_EPREFIX@
SYSCONFDIR   = path.normpath("@sysconfdir@")
DATADIR      = path.normpath("@datadir@")
PORTAGE_BASE = path.normpath("@PORTAGE_BASE@")

portagegroup = "@portagegroup@"
portageuser  = "@portageuser@"
rootuser     = "@rootuser@"
rootuid      = @rootuid@
rootgid      = @rootgid@
