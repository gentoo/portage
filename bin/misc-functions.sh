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

source "${PORTAGE_BIN_PATH:-/usr/lib/portage/bin}/ebuild.sh"

install_qa_check() {

	prepall
	cd "${D}"

	declare -i UNSAFE=0
	for i in $(find "${D}/" -type f -perm -2002); do
		((UNSAFE++))
		vecho "UNSAFE SetGID: $i"
		chmod -s,o-w "$i"
	done
	for i in $(find "${D}/" -type f -perm -4002); do
		((UNSAFE++))
		vecho "UNSAFE SetUID: $i"
		chmod -s,o-w "$i"
	done

	# Now we look for all world writable files.
	for i in $(find "${D}/" -type f -perm -2); do
		vecho -ne '\a'
		vecho "QA Security Notice:"
		vecho "- ${i:${#D}:${#i}} will be a world writable file."
		vecho "- This may or may not be a security problem, most of the time it is one."
		vecho "- Please double check that $PF really needs a world writeable bit and file bugs accordingly."
		sleep 1
	done

	if type -p scanelf > /dev/null && ! hasq binchecks ${RESTRICT}; then
		local qa_var insecure_rpath=0 tmp_quiet=${PORTAGE_QUIET}
		
		# display warnings when using stricter because we die afterwards
		if has stricter ${FEATURES} && ! has stricter ${RESTRICT}; then
			unset PORTAGE_QUIET
		fi
		
		# Make sure we disallow insecure RUNPATH/RPATH's
		# Don't want paths that point to the tree where the package was built
		# (older, broken libtools would do this).  Also check for null paths
		# because the loader will search $PWD when it finds null paths.
		f=$(scanelf -qyRF '%r %p' "${D}" | grep -E "(${PORTAGE_BUILDDIR}|: |::|^:|^ )")
		if [[ -n ${f} ]] ; then
			vecho -ne '\a\n'
			vecho "QA Notice: the following files contain insecure RUNPATH's"
			vecho " Please file a bug about this at http://bugs.gentoo.org/"
			vecho " with the maintaining herd of the package."
			vecho "${f}"
			vecho -ne '\a\n'
			if has stricter ${FEATURES} && ! has stricter ${RESTRICT}; then
				insecure_rpath=1
			else
				vecho "Auto fixing rpaths for ${f}"
				TMPDIR=${PORTAGE_BUILDDIR} scanelf -BXr ${f} -o /dev/null
			fi
		fi

		# Check for setid binaries but are not built with BIND_NOW
		f=$(scanelf -qyRF '%b %p' "${D}")
		if [[ -n ${f} ]] ; then
			vecho -ne '\a\n'
			vecho "QA Notice: the following files are setXid, dyn linked, and using lazy bindings"
			vecho " This combination is generally discouraged.  Try re-emerging the package:"
			vecho " LDFLAGS='-Wl,-z,now' emerge ${PN}"
			vecho "${f}"
			vecho -ne '\a\n'
			die_msg="${die_msg} setXid lazy bindings,"
			sleep 1
		fi

		# TEXTREL's are baaaaaaaad
		# Allow devs to mark things as ignorable ... e.g. things that are
		# binary-only and upstream isn't cooperating (nvidia-glx) ... we
		# allow ebuild authors to set QA_TEXTRELS_arch and QA_TEXTRELS ...
		# the former overrides the latter ... regexes allowed ! :)
		qa_var="QA_TEXTRELS_${ARCH}"
		[[ -n ${!qa_var} ]] && QA_TEXTRELS=${!qa_var}
		[[ -n ${QA_STRICT_TEXTRELS} ]] && QA_TEXTRELS=""
		export QA_TEXTRELS
		f=$(scanelf -qyRF '%t %p' "${D}" | grep -v 'usr/lib/debug/')
		if [[ -n ${f} ]] ; then
			scanelf -qyRF '%T %p' "${PORTAGE_BUILDDIR}"/ &> "${T}"/scanelf-textrel.log
			vecho -ne '\a\n'
			vecho "QA Notice: the following files contain runtime text relocations"
			vecho " Text relocations force the dynamic linker to perform extra"
			vecho " work at startup, waste system resources, and may pose a security"
			vecho " risk.  On some architectures, the code may not even function"
			vecho " properly, if at all."
			vecho " For more information, see http://hardened.gentoo.org/pic-fix-guide.xml"
			vecho " Please include this file in your report:"
			vecho " ${T}/scanelf-textrel.log"
			vecho "${f}"
			vecho -ne '\a\n'
			die_msg="${die_msg} textrels,"
			sleep 1
		fi

		# Also, executable stacks only matter on linux (and just glibc atm ...)
		f=""
		case ${CTARGET:-${CHOST}} in
			*-linux-gnu*)
			# Check for files with executable stacks, but only on arches which
			# are supported at the moment.  Keep this list in sync with
			# http://hardened.gentoo.org/gnu-stack.xml (Arch Status)
			case ${CTARGET:-${CHOST}} in
				i?86*|ia64*|m68k*|s390*|x86_64*)
					# Allow devs to mark things as ignorable ... e.g. things
					# that are binary-only and upstream isn't cooperating ...
					# we allow ebuild authors to set QA_EXECSTACK_arch and
					# QA_EXECSTACK ... the former overrides the latter ...
					# regexes allowed ! :)

					qa_var="QA_EXECSTACK_${ARCH}"
					[[ -n ${!qa_var} ]] && QA_EXECSTACK=${!qa_var}
					[[ -n ${QA_STRICT_EXECSTACK} ]] && QA_EXECSTACK=""
					qa_var="QA_WX_LOAD_${ARCH}"
					[[ -n ${!qa_var} ]] && QA_WX_LOAD=${!qa_var}
					[[ -n ${QA_STRICT_WX_LOAD} ]] && QA_WX_LOAD=""
					export QA_EXECSTACK QA_WX_LOAD
					f=$(scanelf -qyRF '%e %p' "${D}" | grep -v 'usr/lib/debug/')
					;;
			esac
			;;
		esac
		if [[ -n ${f} ]] ; then
			# One more pass to help devs track down the source
			scanelf -qyRF '%e %p' "${PORTAGE_BUILDDIR}"/ &> "${T}"/scanelf-execstack.log
			vecho -ne '\a\n'
			vecho "QA Notice: the following files contain executable stacks"
			vecho " Files with executable stacks will not work properly (or at all!)"
			vecho " on some architectures/operating systems.  A bug should be filed"
			vecho " at http://bugs.gentoo.org/ to make sure the file is fixed."
			vecho " For more information, see http://hardened.gentoo.org/gnu-stack.xml"
			vecho " Please include this file in your report:"
			vecho " ${T}/scanelf-execstack.log"
			vecho "${f}"
			vecho -ne '\a\n'
			die_msg="${die_msg} execstacks"
			sleep 1
		fi

		# Save NEEDED information
		scanelf -qyRF '%p %n' "${D}" | sed -e 's:^:/:' > "${PORTAGE_BUILDDIR}"/build-info/NEEDED

		if [[ ${insecure_rpath} -eq 1 ]] ; then
			die "Aborting due to serious QA concerns with RUNPATH/RPATH"
		elif [[ ${die_msg} != "" ]] && has stricter ${FEATURES} && ! has stricter ${RESTRICT} ; then
			die "Aborting due to QA concerns: ${die_msg}"
		fi

		PORTAGE_QUIET=${tmp_quiet}
	fi

	if [[ ${UNSAFE} > 0 ]] ; then
		die "There are ${UNSAFE} unsafe files. Portage will not install them."
	fi

	if [[ -d ${D}/${D} ]] ; then
		declare -i INSTALLTOD=0
		for i in $(find "${D}/${D}/"); do
			echo "QA Notice: /${i##${D}/${D}} installed in \${D}/\${D}"
			((INSTALLTOD++))
		done
		die "Aborting due to QA concerns: ${INSTALLTOD} files installed in ${D}/${D}"
		unset INSTALLTOD
	fi

	local find_log="${T}/find-portage-log"
	find "${D}"/ -user portage -print0 > "${find_log}"
	if [[ -s ${find_log} ]] ; then
		xargs -0 chown -h ${PORTAGE_INST_UID:-0} < "${find_log}"
	fi
	find "${D}"/ -group portage -print0 > "${find_log}"
	if [[ -s ${find_log} ]] ; then
		xargs -0 chgrp -h ${PORTAGE_INST_GID:-0} < "${find_log}"
	fi
	rm -f "${find_log}"

	# Portage regenerates this on the installed system.
	if [ -f "${D}/usr/share/info/dir.gz" ]; then
		rm -f "${D}/usr/share/info/dir.gz"
	fi

	if hasq multilib-strict ${FEATURES} && [ -x /usr/bin/file -a -x /usr/bin/find -a \
	     -n "${MULTILIB_STRICT_DIRS}" -a -n "${MULTILIB_STRICT_DENY}" ]; then
		MULTILIB_STRICT_EXEMPT=$(echo ${MULTILIB_STRICT_EXEMPT:-"(perl5|gcc|gcc-lib|debug|portage)"} | sed -e 's:\([(|)]\):\\\1:g')
		for dir in ${MULTILIB_STRICT_DIRS}; do
			[ -d "${D}/${dir}" ] || continue
			for file in $(find ${D}/${dir} -type f | grep -v "^${D}/${dir}/${MULTILIB_STRICT_EXEMPT}"); do
				file ${file} | egrep -q "${MULTILIB_STRICT_DENY}" && die "File ${file} matches a file type that is not allowed in ${dir}"
			done
		done
	fi

}


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
		find "${root}" -path ${no_inst} -exec rm -fR {} \; >/dev/null
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
		vecho ">>> Performing suid scan in ${IMAGE}"
		for i in $(find ${IMAGE}/ -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [ -s "${sfconf}" ]; then
				suid="$(grep ^${i/${IMAGE}/}$ ${sfconf})"
				if [ "${suid}" = "${i/${IMAGE}/}" ]; then
					vecho "- ${i/${IMAGE}/} is an approved suid file"
				else
					vecho ">>> Removing sbit on non registered ${i/${IMAGE}/}"
					for x in 5 4 3 2 1 0; do echo -ne "\a"; sleep 0.25 ; done
					vecho -ne "\a"
					ls_ret=$(ls -ldh "${i}")
					chmod ugo-s "${i}"
					grep ^#${i/${IMAGE}/}$ ${sfconf} > /dev/null || {
						# sandbox prevents us from writing directly
						# to files outside of the sandbox, but this
						# can easly be bypassed using the addwrite() function
						addwrite "${sfconf}"
						vecho ">>> Appending commented out entry to ${sfconf} for ${PF}"
						echo "## ${ls_ret%${IMAGE}*}${ls_ret#*${IMAGE}}" >> ${sfconf}
						echo "#${i/${IMAGE}/}" >> ${sfconf}
						# no delwrite() eh?
						# delwrite ${sconf}
					}
				fi
			else
				vecho "suidctl feature set but you are lacking a ${sfconf}"
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
			vecho ">>> Setting SELinux security labels"
			(
				eval "$(/usr/sbin/selinuxconfig)" || \
					die "Failed to determine SELinux policy paths.";
	
				addwrite /selinux/context;
	
				/usr/sbin/setfiles "${file_contexts_path}" -r "${IMAGE}" "${IMAGE}";
			) || die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			vecho "!!! Unable to set SELinux security labels"
		fi
	fi
}

dyn_package() {
	cd "${PORTAGE_BUILDDIR}/image"
	install_mask "${PORTAGE_BUILDDIR}/image" ${PKG_INSTALL_MASK}
	local pkg_dest="${PKGDIR}/All/${PF}.tbz2"
	local pkg_tmp="${PKGDIR}/All/${PF}.tbz2.$$"
	# Sandbox is disabled in case the user wants to use a symlink
	# for $PKGDIR and/or $PKGDIR/All.
	export SANDBOX_ON="0"
	tar cpvf - ./ | bzip2 -f > "${pkg_tmp}" || die "Failed to create tarball"
	cd ..
	python -c "import xpak; t=xpak.tbz2('${pkg_tmp}'); t.recompose('${PORTAGE_BUILDDIR}/build-info')"
	if [ $? -ne 0 ]; then
		rm -f "${pkg_tmp}"
		die "Failed to append metadata to the tbz2 file"
	fi
	mv -f "${pkg_tmp}" "${pkg_dest}" || die "Failed to move tbz2 to ${pkg_dest}"
	ln -sf "../All/${PF}.tbz2" "${PKGDIR}/${CATEGORY}/${PF}.tbz2" || die "Failed to create symlink in ${PKGDIR}/${CATEGORY}"
	vecho ">>> Done."
	cd "${PORTAGE_BUILDDIR}"
	touch .packaged || die "Failed to 'touch .packaged' in ${PORTAGE_BUILDDIR}"
}

dyn_spec() {
	tar czf "/usr/src/redhat/SOURCES/${PF}.tar.gz" "${O}/${PF}.ebuild" "${O}/files" || die "Failed to create base rpm tarball."

	cat <<__END1__ > ${PF}.spec
Summary: ${DESCRIPTION}
Name: ${PN}
Version: ${PV}
Release: ${PR}
Copyright: GPL
Group: portage/${CATEGORY}
Source: ${PF}.tar.gz
Buildroot: ${D}
%description
${DESCRIPTION}

${HOMEPAGE}

%prep
%setup -c

%build

%install

%clean

%files
/
__END1__

}

dyn_rpm() {
	addwrite /usr/src/redhat/
	addwrite ${RPMDIR}
	dyn_spec
	rpmbuild -bb "${PF}.spec" || die "Failed to integrate rpm spec file"
	install -D "/usr/src/redhat/RPMS/i386/${PN}-${PV}-${PR}.i386.rpm" "${RPMDIR}/${CATEGORY}/${PN}-${PV}-${PR}.rpm" || die "Failed to move rpm"
}

if [ -n "${MISC_FUNCTIONS_ARGS}" ]; then
	[ "$PORTAGE_DEBUG" == "1" ] && set -x
	for x in ${MISC_FUNCTIONS_ARGS}; do
		${x}
	done
fi

true
