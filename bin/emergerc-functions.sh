#!/bin/bash
# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

register_firstEmerge_hook() {
	local x
	for x in $* ; do
		has $x $EBUILD_FIRST_EMERGE_HOOKS || \
			export EBUILD_FIRST_EMERGE_HOOKS="$EBUILD_FIRST_EMERGE_HOOKS $x"
	done
}

firstEmerge_hooks() {
	local x
	for x in $EBUILD_FIRST_EMERGE_HOOKS ; do
		$x
	done
}
