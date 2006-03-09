#!/bin/bash
# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$
#
# Miscellaneous shell functions that make use of the ebuild env but don't need
# to be included directly in ebuild.sh.
#
# We're sourcing ebuild.sh here so that we inherit all of it's goodness,
# including bashrc trickery.  This approach allows us to do our miscellaneous
# shell work withing the same env that ebuild.sh has, but without polluting
# ebuild.sh itself with unneeded logic and shell code.
#
# XXX hack: clear the args so ebuild.sh doesn't see them
MISC_FUNCTIONS_ARGS="$@"
shift $#
source /usr/lib/portage/bin/ebuild.sh

dyn_package() {
	cd "${PORTAGE_BUILDDIR}/image"
	install_mask "${PORTAGE_BUILDDIR}/image" ${PKG_INSTALL_MASK}
	tar cpvf - ./ | bzip2 -f > ../bin.tar.bz2 || die "Failed to create tarball"
	cd ..
	xpak build-info inf.xpak
	tbz2tool join bin.tar.bz2 inf.xpak "${PF}.tbz2"
	addwrite "${PKGDIR}"
	mv "${PF}.tbz2" "${PKGDIR}/All" || die "Failed to move tbz2 to ${PKGDIR}/All"
	rm -f inf.xpak bin.tar.bz2
	if [ ! -d "${PKGDIR}/${CATEGORY}" ]; then
		install -d "${PKGDIR}/${CATEGORY}"
	fi
	ln -sf "../All/${PF}.tbz2" "${PKGDIR}/${CATEGORY}/${PF}.tbz2" || die "Failed to create symlink in ${PKGDIR}/${CATEGORY}"
	echo ">>> Done."
	cd "${PORTAGE_BUILDDIR}"
	touch .packaged || die "Failed to 'touch .packaged' in ${PORTAGE_BUILDDIR}"
}

if [ -n "${MISC_FUNCTIONS_ARGS}" ]; then
	[ "$PORTAGE_DEBUG" == "1" ] && set -x
	for x in ${MISC_FUNCTIONS_ARGS}; do
		${x}
	done
fi

true
