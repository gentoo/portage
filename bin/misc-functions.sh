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

install_mask() {
	local root="$1"
	shift
	local install_mask="$*"

	# we don't want globbing for initial expansion, but afterwards, we do
	local shopts=$-
	set -o noglob
	for no_inst in ${install_mask}; do
		set +o noglob
		einfo "Removing ${no_inst}"
		# normal stuff
		rm -Rf ${root}/${no_inst} >&/dev/null

		# we also need to handle globs (*.a, *.h, etc)
		find "${root}" -name ${no_inst} -exec rm -fR {} \; >/dev/null
	done
	# set everything back the way we found it
	set +o noglob
	set -${shopts}
}

preinst_mask() {
	if [ -z "$IMAGE" ]; then
		 eerror "${FUNCNAME}: IMAGE is unset"
		 return 1
	fi
	# remove man pages, info pages, docs if requested
	for f in man info doc; do
		if hasq no${f} $FEATURES; then
			INSTALL_MASK="${INSTALL_MASK} /usr/share/${f}"
		fi
	done

	install_mask "${IMAGE}" ${INSTALL_MASK}

	# remove share dir if unnessesary
	if hasq nodoc $FEATURES -o hasq noman $FEATURES -o hasq noinfo $FEATURES; then
		rmdir "${IMAGE}/usr/share" &> /dev/null
	fi
}

preinst_sfperms() {
	if [ -z "$IMAGE" ]; then
		 eerror "${FUNCNAME}: IMAGE is unset"
		 return 1
	fi
	# Smart FileSystem Permissions
	if hasq sfperms $FEATURES; then
		for i in $(find ${IMAGE}/ -type f -perm -4000); do
			ebegin ">>> SetUID: [chmod go-r] $i "
			chmod go-r "$i"
			eend $?
		done
		for i in $(find ${IMAGE}/ -type f -perm -2000); do
			ebegin ">>> SetGID: [chmod o-r] $i "
			chmod o-r "$i"
			eend $?
		done
	fi
}

preinst_suid_scan() {
	if [ -z "$IMAGE" ]; then
		 eerror "${FUNCNAME}: IMAGE is unset"
		 return 1
	fi
	# total suid control.
	if hasq suidctl $FEATURES; then
		sfconf=/etc/portage/suidctl.conf
		echo ">>> Preforming suid scan in ${IMAGE}"
		for i in $(find ${IMAGE}/ -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [ -s "${sfconf}" ]; then
				suid="`grep ^${i/${IMAGE}/}$ ${sfconf}`"
				if [ "${suid}" = "${i/${IMAGE}/}" ]; then
					echo "- ${i/${IMAGE}/} is an approved suid file"
				else
					echo ">>> Removing sbit on non registered ${i/${IMAGE}/}"
					for x in 5 4 3 2 1 0; do echo -ne "\a"; sleep 0.25 ; done
					echo -ne "\a"
					chmod ugo-s "${i}"
					grep ^#${i/${IMAGE}/}$ ${sfconf} > /dev/null || {
						# sandbox prevents us from writing directly
						# to files outside of the sandbox, but this
						# can easly be bypassed using the addwrite() function
						addwrite "${sfconf}"
						echo ">>> Appending commented out entry to ${sfconf} for ${PF}"
						ls_ret=`ls -ldh "${i}"`
						echo "## ${ls_ret%${IMAGE}*}${ls_ret#*${IMAGE}}" >> ${sfconf}
						echo "#${i/${IMAGE}/}" >> ${sfconf}
						# no delwrite() eh?
						# delwrite ${sconf}
					}
				fi
			else
				echo "suidctl feature set but you are lacking a ${sfconf}"
			fi
		done
	fi
}

preinst_selinux_labels() {
	if [ -z "$IMAGE" ]; then
		 eerror "${FUNCNAME}: IMAGE is unset"
		 return 1
	fi
	if hasq selinux ${FEATURES}; then
		# SELinux file labeling (needs to always be last in dyn_preinst)
		# only attempt to label if setfiles is executable
		# and 'context' is available on selinuxfs.
		if [ -f /selinux/context -a -x /usr/sbin/setfiles -a -x /usr/sbin/selinuxconfig ]; then
			echo ">>> Setting SELinux security labels"
			(
				eval "$(/usr/sbin/selinuxconfig)" || \
					die "Failed to determine SELinux policy paths.";
	
				addwrite /selinux/context;
	
				/usr/sbin/setfiles "${file_contexts_path}" -r "${IMAGE}" "${IMAGE}";
			) || die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			echo "!!! Unable to set SELinux security labels"
		fi
	fi
}

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
