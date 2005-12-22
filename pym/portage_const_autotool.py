# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2
# $Id:$

# all vars that are to wind up in portage_const must have their name listed in __all__

__all__ = ["PREFIX", "SYSCONFDIR", "PORTAGE_BASE", "portageuser", "portagegroup", "rootuser", "wheelgid", "wheelgroup"]

PREFIX="@DOMAIN_PREFIX@/"
SYSCONFDIR="@sysconfdir@/"
PORTAGE_BASE="@PORTAGE_BASE@/"
portagegroup="@portagegroup@"
portageuser="@portageuser@"
rootuser="@rootuser@"
wheelgid="@wheelgid@"
wheelgroup"@wheelgroup@
