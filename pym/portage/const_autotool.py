# Copyright: 2005-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

# all vars that are to wind up in portage_const must have their name listed in __all__

__all__ = ["EPREFIX", "SYSCONFDIR", "DATAROOTDIR", "PORTAGE_BASE",
		"portageuser", "portagegroup", "rootuser", "rootuid"]

from os import path

EPREFIX=path.normpath("@DOMAIN_PREFIX@")
SYSCONFDIR=path.normpath("@sysconfdir@")
DATAROOTDIR=path.normpath("@datarootdir@")
PORTAGE_BASE=path.normpath("@PORTAGE_BASE@")
portagegroup="@portagegroup@"
portageuser="@portageuser@"
rootuser="@rootuser@"
rootuid=@rootuid@
