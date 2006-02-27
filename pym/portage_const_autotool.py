# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id:$

# all vars that are to wind up in portage_const must have their name listed in __all__

__all__ = ["PREFIX", "SYSCONFDIR", "PORTAGE_BASE", "portageuser", "portagegroup", "rootuser", "rootuid", "wheelgid", "wheelgroup"]

from os import path

PREFIX=path.normpath("@DOMAIN_PREFIX@")
SYSCONFDIR=path.normpath("@sysconfdir@")
PORTAGE_BASE=path.normpath("@PORTAGE_BASE@")
portagegroup="@portagegroup@"
portageuser="@portageuser@"
rootuser="@rootuser@"
rootuid="@rootuid@"
wheelgid="@wheelgid@"
wheelgroup="@wheelgroup@"
