#!/bin/bash
# Copyright 1999-2018 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
#
# Miscellaneous shell functions that make use of the ebuild env but don't need
# to be included directly in ebuild.sh.
#
# We're sourcing ebuild.sh here so that we inherit all of it's goodness,
# including bashrc trickery.  This approach allows us to do our miscellaneous
# shell work within the same env that ebuild.sh has, but without polluting
# ebuild.sh itself with unneeded logic and shell code.
#
# XXX hack: clear the args so ebuild.sh doesn't see them
MISC_FUNCTIONS_ARGS="$@"
shift $#

source "${PORTAGE_BIN_PATH}/ebuild.sh" || exit 1

install_symlink_html_docs() {
	if ! ___eapi_has_prefix_variables; then
		local ED=${D}
	fi
	cd "${ED}" || die "cd failed"
	#symlink the html documentation (if DOC_SYMLINKS_DIR is set in make.conf)
	if [ -n "${DOC_SYMLINKS_DIR}" ] ; then
		local mydocdir docdir
		for docdir in "${HTMLDOC_DIR:-does/not/exist}" "${PF}/html" "${PF}/HTML" "${P}/html" "${P}/HTML" ; do
			if [ -d "usr/share/doc/${docdir}" ] ; then
				mydocdir="/usr/share/doc/${docdir}"
			fi
		done
		if [ -n "${mydocdir}" ] ; then
			local mysympath
			if [ -z "${SLOT}" -o "${SLOT%/*}" = "0" ] ; then
				mysympath="${DOC_SYMLINKS_DIR}/${CATEGORY}/${PN}"
			else
				mysympath="${DOC_SYMLINKS_DIR}/${CATEGORY}/${PN}-${SLOT%/*}"
			fi
			einfo "Symlinking ${mysympath} to the HTML documentation"
			dodir "${DOC_SYMLINKS_DIR}/${CATEGORY}"
			dosym "${mydocdir}" "${mysympath}"
		fi
	fi
}

# replacement for "readlink -f" or "realpath"
READLINK_F_WORKS=""
canonicalize() {
	if [[ -z ${READLINK_F_WORKS} ]] ; then
		if [[ $(readlink -f -- /../ 2>/dev/null) == "/" ]] ; then
			READLINK_F_WORKS=true
		else
			READLINK_F_WORKS=false
		fi
	fi
	if ${READLINK_F_WORKS} ; then
		readlink -f -- "$@"
		return
	fi

	local f=$1 b n=10 wd=$(pwd)
	while (( n-- > 0 )); do
		while [[ ${f: -1} = / && ${#f} -gt 1 ]]; do
			f=${f%/}
		done
		b=${f##*/}
		cd "${f%"${b}"}" 2>/dev/null || break
		if [[ ! -L ${b} ]]; then
			f=$(pwd -P)
			echo "${f%/}/${b}"
			cd "${wd}"
			return 0
		fi
		f=$(readlink "${b}")
	done
	cd "${wd}"
	return 1
}

install_qa_check() {
	local d f i qa_var x paths qa_checks=() checks_run=()
	if ! ___eapi_has_prefix_variables; then
		local EPREFIX= ED=${D}
	fi

	cd "${ED}" || die "cd failed"

	# Collect the paths for QA checks, highest prio first.
	paths=(
		# sysadmin overrides
		"${PORTAGE_OVERRIDE_EPREFIX}"/usr/local/lib/install-qa-check.d
		# system-wide package installs
		"${PORTAGE_OVERRIDE_EPREFIX}"/usr/lib/install-qa-check.d
	)

	# Now repo-specific checks.
	# (yes, PORTAGE_ECLASS_LOCATIONS contains repo paths...)
	for d in "${PORTAGE_ECLASS_LOCATIONS[@]}"; do
		paths+=(
			"${d}"/metadata/install-qa-check.d
		)
	done

	paths+=(
		# Portage built-in checks
		"${PORTAGE_OVERRIDE_EPREFIX}"/usr/lib/portage/install-qa-check.d
		"${PORTAGE_BIN_PATH}"/install-qa-check.d
	)

	# Collect file names of QA checks. We need them early to support
	# overrides properly.
	for d in "${paths[@]}"; do
		for f in "${d}"/*; do
			[[ -f ${f} ]] && qa_checks+=( "${f##*/}" )
		done
	done

	# Now we need to sort the filenames lexically, and process
	# them in order.
	while read -r -d '' f; do
		# Find highest priority file matching the basename.
		for d in "${paths[@]}"; do
			[[ -f ${d}/${f} ]] && break
		done

		# Run in a subshell to treat it like external script,
		# but use 'source' to pass all variables through.
		(
			# Allow inheriting eclasses.
			# XXX: we want this only in repository-wide checks.
			_IN_INSTALL_QA_CHECK=1
			source "${d}/${f}" || eerror "Post-install QA check ${f} failed to run"
		)
	done < <(printf "%s\0" "${qa_checks[@]}" | LC_ALL=C sort -u -z)

	if has chflags $FEATURES ; then
		# Save all the file flags for restoration afterwards.
		mtree -c -p "${ED}" -k flags > "${T}/bsdflags.mtree"
		# Remove all the file flags so that we can do anything necessary.
		chflags -R noschg,nouchg,nosappnd,nouappnd "${ED}"
		chflags -R nosunlnk,nouunlnk "${ED}" 2>/dev/null
	fi

	[[ -d ${ED%/}/usr/share/info ]] && prepinfo

	# If binpkg-docompress is enabled, apply compression before creating
	# the binary package.
	if has binpkg-docompress ${FEATURES}; then
		"${PORTAGE_BIN_PATH}"/ecompress --queue "${PORTAGE_DOCOMPRESS[@]}"
		"${PORTAGE_BIN_PATH}"/ecompress --ignore "${PORTAGE_DOCOMPRESS_SKIP[@]}"
		"${PORTAGE_BIN_PATH}"/ecompress --dequeue
	fi

	# If binpkg-dostrip is enabled, apply stripping before creating
	# the binary package.
	# Note: disabling it won't help with packages calling prepstrip directly.
	if has binpkg-dostrip ${FEATURES}; then
		export STRIP_MASK
		if ___eapi_has_dostrip; then
			"${PORTAGE_BIN_PATH}"/estrip --queue "${PORTAGE_DOSTRIP[@]}"
			"${PORTAGE_BIN_PATH}"/estrip --ignore "${PORTAGE_DOSTRIP_SKIP[@]}"
			"${PORTAGE_BIN_PATH}"/estrip --dequeue
		else
			prepallstrip
		fi
	fi

	if has chflags $FEATURES ; then
		# Restore all the file flags that were saved earlier on.
		mtree -U -e -p "${ED}" -k flags < "${T}/bsdflags.mtree" &> /dev/null
	fi

	# Create NEEDED.ELF.2 regardless of RESTRICT=binchecks, since this info is
	# too useful not to have (it's required for things like preserve-libs), and
	# it's tempting for ebuild authors to set RESTRICT=binchecks for packages
	# containing pre-built binaries.
	if type -P scanelf > /dev/null ; then
		# Save NEEDED information after removing self-contained providers
		rm -f "$PORTAGE_BUILDDIR"/build-info/NEEDED{,.ELF.2}

		# We don't use scanelf -q, since that would omit libraries like
		# musl's /usr/lib/libc.so which do not have any DT_NEEDED or
		# DT_SONAME settings. Since we don't use scanelf -q, we have to
		# handle the special rpath value "  -  " below.
		scanelf_output=$(scanelf -yRBF '%a;%p;%S;%r;%n' "${D%/}/")

		case $? in
			0)
				# Proceed
				;;
			159)
				# Unknown syscall
				eerror "Failed to run scanelf (unknown syscall)"

				if [[ -z ${PORTAGE_NO_SCANELF_CHECK} ]]; then
					# Abort only if the special recovery variable isn't set
					eerror "Please upgrade pax-utils with:"
					eerror " PORTAGE_NO_SCANELF_CHECK=1 emerge -v1 app-misc/pax-utils"
					eerror "Aborting to avoid corrupting metadata"
					die "${0##*/}: Failed to run scanelf! Update pax-utils?"
				fi
				;;
			*)
				# Failed in another way
				eerror "Failed to run scanelf (returned: $?)!"

				if [[ -z ${PORTAGE_NO_SCANELF_CHECK} ]]; then
					# Abort only if the special recovery variable isn't set
					eerror "Please report this bug at https://bugs.gentoo.org/!"
					eerror "It may be possible to re-emerge pax-utils with:"
					eerror " PORTAGE_NO_SCANELF_CHECK=1 emerge -v1 app-misc/pax-utils"
					eerror "Aborting to avoid corrupting metadata"
					die "${0##*/}: Failed to run scanelf!"
				fi
				;;
		esac

		if [[ -n ${scanelf_output} ]]; then
			while IFS= read -r l; do
				arch=${l%%;*}; l=${l#*;}
				obj="/${l%%;*}"; l=${l#*;}
				soname=${l%%;*}; l=${l#*;}
				rpath=${l%%;*}; l=${l#*;}; [ "${rpath}" = "  -  " ] && rpath=""
				needed=${l%%;*}; l=${l#*;}

				# Infer implicit soname from basename (bug 715162).
				if [[ -z ${soname} && $(file "${D%/}${obj}") == *"SB shared object"* ]]; then
					soname=${obj##*/}
				fi

				echo "${obj} ${needed}"	>> "${PORTAGE_BUILDDIR}"/build-info/NEEDED
				echo "${arch#EM_};${obj};${soname};${rpath};${needed}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED.ELF.2
			done <<< ${scanelf_output}
		fi

		[ -n "${QA_SONAME_NO_SYMLINK}" ] && \
			echo "${QA_SONAME_NO_SYMLINK}" > \
			"${PORTAGE_BUILDDIR}"/build-info/QA_SONAME_NO_SYMLINK

		if [[ -s ${PORTAGE_BUILDDIR}/build-info/NEEDED.ELF.2 ]]; then
			if grep -qs '<stabilize-allarches/>' "${EBUILD%/*}/metadata.xml"; then
				eqawarn "QA Notice: <stabilize-allarches/> found on package installing ELF files"
			fi

			if has binchecks ${PORTAGE_RESTRICT}; then
				eqawarn "QA Notice: RESTRICT=binchecks prevented checks on these ELF files:"
				eqawarn "$(while read -r x; do x=${x#*;} ; x=${x%%;*} ; echo "${x#${EPREFIX}}" ; done < "${PORTAGE_BUILDDIR}"/build-info/NEEDED.ELF.2)"
			fi
		fi
	fi

	# Portage regenerates this on the installed system.
	rm -f "${ED%/}"/usr/share/info/dir{,.gz,.bz2} || die "rm failed!"
}

__dyn_instprep() {
	if [[ -e ${PORTAGE_BUILDDIR}/.instprepped ]] ; then
		__vecho ">>> It appears that '$PF' is already instprepped; skipping."
		__vecho ">>> Remove '${PORTAGE_BUILDDIR}/.instprepped' to force instprep."
		return 0
	fi

	if has chflags ${FEATURES}; then
		# Save all the file flags for restoration afterwards.
		mtree -c -p "${ED}" -k flags > "${T}/bsdflags.mtree"
		# Remove all the file flags so that we can do anything necessary.
		chflags -R noschg,nouchg,nosappnd,nouappnd "${ED}"
		chflags -R nosunlnk,nouunlnk "${ED}" 2>/dev/null
	fi

	# If binpkg-docompress is disabled, we need to apply compression
	# before installing.
	if ! has binpkg-docompress ${FEATURES}; then
		"${PORTAGE_BIN_PATH}"/ecompress --queue "${PORTAGE_DOCOMPRESS[@]}"
		"${PORTAGE_BIN_PATH}"/ecompress --ignore "${PORTAGE_DOCOMPRESS_SKIP[@]}"
		"${PORTAGE_BIN_PATH}"/ecompress --dequeue
	fi

	# If binpkg-dostrip is disabled, apply stripping before creating
	# the binary package.
	if ! has binpkg-dostrip ${FEATURES}; then
		export STRIP_MASK
		if ___eapi_has_dostrip; then
			"${PORTAGE_BIN_PATH}"/estrip --queue "${PORTAGE_DOSTRIP[@]}"
			"${PORTAGE_BIN_PATH}"/estrip --ignore "${PORTAGE_DOSTRIP_SKIP[@]}"
			"${PORTAGE_BIN_PATH}"/estrip --dequeue
		else
			prepallstrip
		fi
	fi

	if has chflags ${FEATURES}; then
		# Restore all the file flags that were saved earlier on.
		mtree -U -e -p "${ED}" -k flags < "${T}/bsdflags.mtree" &> /dev/null
	fi

	>> "${PORTAGE_BUILDDIR}/.instprepped" || \
		die "Failed to create ${PORTAGE_BUILDDIR}/.instprepped"
}

preinst_qa_check() {
	postinst_qa_check preinst
}

postinst_qa_check() {
	local d f paths qa_checks=() PORTAGE_QA_PHASE=${1:-postinst}
	if ! ___eapi_has_prefix_variables; then
		local EPREFIX= EROOT=${ROOT}
	fi

	cd "${EROOT:-/}" || die "cd failed"

	# Collect the paths for QA checks, highest prio first.
	paths=(
		# sysadmin overrides
		"${PORTAGE_OVERRIDE_EPREFIX}"/usr/local/lib/${PORTAGE_QA_PHASE}-qa-check.d
		# system-wide package installs
		"${PORTAGE_OVERRIDE_EPREFIX}"/usr/lib/${PORTAGE_QA_PHASE}-qa-check.d
	)

	# Now repo-specific checks.
	# (yes, PORTAGE_ECLASS_LOCATIONS contains repo paths...)
	for d in "${PORTAGE_ECLASS_LOCATIONS[@]}"; do
		paths+=(
			"${d}"/metadata/${PORTAGE_QA_PHASE}-qa-check.d
		)
	done

	paths+=(
		# Portage built-in checks
		"${PORTAGE_OVERRIDE_EPREFIX}"/usr/lib/portage/${PORTAGE_QA_PHASE}-qa-check.d
		"${PORTAGE_BIN_PATH}"/${PORTAGE_QA_PHASE}-qa-check.d
	)

	# Collect file names of QA checks. We need them early to support
	# overrides properly.
	for d in "${paths[@]}"; do
		for f in "${d}"/*; do
			[[ -f ${f} ]] && qa_checks+=( "${f##*/}" )
		done
	done

	# Now we need to sort the filenames lexically, and process
	# them in order.
	while read -r -d '' f; do
		# Find highest priority file matching the basename.
		for d in "${paths[@]}"; do
			[[ -f ${d}/${f} ]] && break
		done

		# Run in a subshell to treat it like external script,
		# but use 'source' to pass all variables through.
		(
			# Allow inheriting eclasses.
			# XXX: we want this only in repository-wide checks.
			_IN_INSTALL_QA_CHECK=1
			source "${d}/${f}" || eerror "Post-${PORTAGE_QA_PHASE} QA check ${f} failed to run"
		)
	done < <(printf "%s\0" "${qa_checks[@]}" | LC_ALL=C sort -u -z)
}

preinst_mask() {
	# Remove man pages, info pages, docs if requested. This is
	# implemented in bash in order to respect INSTALL_MASK settings
	# from bashrc.
	local f x
	for f in man info doc; do
		if has no${f} ${FEATURES}; then
			INSTALL_MASK+=" /usr/share/${f}"
		fi
	done

	# Store modified variables in build-info.
	cd "${PORTAGE_BUILDDIR}"/build-info || die
	set -f

	IFS=$' \t\n\r'
	for f in INSTALL_MASK; do
		x=$(echo -n ${!f})
		[[ -n ${x} ]] && echo "${x}" > "${f}"
	done
	set +f
}

preinst_sfperms() {
	if [ -z "${D}" ]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi

	if ! ___eapi_has_prefix_variables; then
		local ED=${D}
	fi

	# Smart FileSystem Permissions
	if has sfperms $FEATURES; then
		local i
		find "${ED}" -type f -perm -4000 -print0 | \
		while read -r -d $'\0' i ; do
			if [ -n "$(find "$i" -perm -2000)" ] ; then
				ebegin ">>> SetUID and SetGID: [chmod o-r] ${i#${ED%/}}"
				chmod o-r "$i"
				eend $?
			else
				ebegin ">>> SetUID: [chmod go-r] ${i#${ED%/}}"
				chmod go-r "$i"
				eend $?
			fi
		done
		find "${ED}" -type f -perm -2000 -print0 | \
		while read -r -d $'\0' i ; do
			if [ -n "$(find "$i" -perm -4000)" ] ; then
				# This case is already handled
				# by the SetUID check above.
				true
			else
				ebegin ">>> SetGID: [chmod o-r] ${i#${ED%/}}"
				chmod o-r "$i"
				eend $?
			fi
		done
	fi
}

preinst_suid_scan() {
	if [ -z "${D}" ]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi

	if ! ___eapi_has_prefix_variables; then
		local ED=${D}
	fi

	# total suid control.
	if has suidctl $FEATURES; then
		local i sfconf x
		sfconf=${PORTAGE_CONFIGROOT}etc/portage/suidctl.conf
		# sandbox prevents us from writing directly
		# to files outside of the sandbox, but this
		# can easly be bypassed using the addwrite() function
		addwrite "${sfconf}"
		__vecho ">>> Performing suid scan in ${ED}"
		for i in $(find "${ED}" -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [ -s "${sfconf}" ]; then
				install_path=${i#${ED%/}}
				if grep -q "^${install_path}\$" "${sfconf}" ; then
					__vecho "- ${install_path} is an approved suid file"
				else
					__vecho ">>> Removing sbit on non registered ${install_path}"
					LC_ALL=C sleep 1.5
					ls_ret=$(ls -ldh "${i}")
					chmod ugo-s "${i}"
					grep "^#${install_path}$" "${sfconf}" > /dev/null || {
						__vecho ">>> Appending commented out entry to ${sfconf} for ${PF}"
						echo "## ${ls_ret%${ED%/}*}${install_path}" >> "${sfconf}"
						echo "#${install_path}" >> "${sfconf}"
						# no delwrite() eh?
						# delwrite ${sconf}
					}
				fi
			else
				__vecho "suidctl feature set but you are lacking a ${sfconf}"
			fi
		done
	fi
}

preinst_selinux_labels() {
	if [ -z "${D}" ]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi
	if has selinux ${FEATURES}; then
		# SELinux file labeling (needs to execute after preinst)
		# only attempt to label if setfiles is executable
		# and 'context' is available on selinuxfs.
		if [ -f /sys/fs/selinux/context -a -x /usr/sbin/setfiles -a -x /usr/sbin/selinuxconfig ]; then
			__vecho ">>> Setting SELinux security labels"
			(
				eval "$(/usr/sbin/selinuxconfig)" || \
					die "Failed to determine SELinux policy paths.";

				addwrite /sys/fs/selinux/context

				/usr/sbin/setfiles -F -r "${D}" "${file_contexts_path}" "${D}"
			) || die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			__vecho "!!! Unable to set SELinux security labels"
		fi
	fi
}

__dyn_package() {

	if ! ___eapi_has_prefix_variables; then
		local EPREFIX=
	fi

	# Make sure $PWD is not ${D} so that we don't leave gmon.out files
	# in there in case any tools were built with -pg in CFLAGS.
	cd "${T}" || die

	local tar_options=""
	[[ $PORTAGE_VERBOSE = 1 ]] && tar_options+=" -v"
	has xattr ${FEATURES} && [[ $(tar --help 2> /dev/null) == *--xattrs* ]] && tar_options+=" --xattrs"
	# Sandbox is disabled in case the user wants to use a symlink
	# for $PKGDIR and/or $PKGDIR/All.
	export SANDBOX_ON="0"
	[ -z "${PORTAGE_BINPKG_TMPFILE}" ] && \
		die "PORTAGE_BINPKG_TMPFILE is unset"
	mkdir -p "${PORTAGE_BINPKG_TMPFILE%/*}" || die "mkdir failed"
	[ -z "${PORTAGE_COMPRESSION_COMMAND}" ] && \
        die "PORTAGE_COMPRESSION_COMMAND is unset"
	tar $tar_options -cf - $PORTAGE_BINPKG_TAR_OPTS -C "${D}" . | \
		$PORTAGE_COMPRESSION_COMMAND > "$PORTAGE_BINPKG_TMPFILE"
	assert "failed to pack binary package: '$PORTAGE_BINPKG_TMPFILE'"
	PYTHONPATH=${PORTAGE_PYTHONPATH:-${PORTAGE_PYM_PATH}} \
		"${PORTAGE_PYTHON:-/usr/bin/python}" "$PORTAGE_BIN_PATH"/xpak-helper.py recompose \
		"$PORTAGE_BINPKG_TMPFILE" "$PORTAGE_BUILDDIR/build-info"
	if [ $? -ne 0 ]; then
		rm -f "${PORTAGE_BINPKG_TMPFILE}"
		die "Failed to append metadata to the tbz2 file"
	fi
	local md5_hash=""
	if type md5sum &>/dev/null ; then
		md5_hash=$(md5sum "${PORTAGE_BINPKG_TMPFILE}")
		md5_hash=${md5_hash%% *}
	elif type md5 &>/dev/null ; then
		md5_hash=$(md5 "${PORTAGE_BINPKG_TMPFILE}")
		md5_hash=${md5_hash##* }
	fi
	[ -n "${md5_hash}" ] && \
		echo ${md5_hash} > "${PORTAGE_BUILDDIR}"/build-info/BINPKGMD5
	__vecho ">>> Done."

	cd "${PORTAGE_BUILDDIR}"
	>> "$PORTAGE_BUILDDIR/.packaged" || \
		die "Failed to create $PORTAGE_BUILDDIR/.packaged"
}

__dyn_spec() {
	local sources_dir=${T}/rpmbuild/SOURCES
	mkdir -p "${sources_dir}"
	declare -a tar_args=("${EBUILD}")
	[[ -d ${FILESDIR} ]] && tar_args=("${EBUILD}" "${FILESDIR}")
	tar czf "${sources_dir}/${PF}.tar.gz" \
		"${tar_args[@]}" || \
		die "Failed to create base rpm tarball."

	cat <<__END1__ > ${PF}.spec
Summary: ${DESCRIPTION}
Name: ${PN}
Version: ${PV}
Release: ${PR}
License: GPL
Group: portage/${CATEGORY}
Source: ${PF}.tar.gz
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

__dyn_rpm() {
	if ! ___eapi_has_prefix_variables; then
		local EPREFIX=
	fi

	cd "${T}" || die "cd failed"
	local machine_name=${CHOST%%-*}
	local dest_dir=${T}/rpmbuild/RPMS/${machine_name}
	addwrite "${RPMDIR}"
	__dyn_spec
	HOME=${T} \
	rpmbuild -bb --clean --nodeps --rmsource "${PF}.spec" --buildroot "${D}" --target "${CHOST}" || die "Failed to integrate rpm spec file"
	install -D "${dest_dir}/${PN}-${PV}-${PR}.${machine_name}.rpm" \
		"${RPMDIR}/${CATEGORY}/${PN}-${PV}-${PR}.rpm" || \
		die "Failed to move rpm"
}

die_hooks() {
	[[ -f $PORTAGE_BUILDDIR/.die_hooks ]] && return
	local x
	for x in $EBUILD_DEATH_HOOKS ; do
		$x >&2
	done
	> "$PORTAGE_BUILDDIR/.die_hooks"
}

success_hooks() {
	local x
	for x in $EBUILD_SUCCESS_HOOKS ; do
		$x
	done
}

install_hooks() {
	local hooks_dir="${PORTAGE_CONFIGROOT}etc/portage/hooks/install"
	local fp
	local ret=0
	shopt -s nullglob
	for fp in "${hooks_dir}"/*; do
		if [ -x "$fp" ]; then
			"$fp"
			ret=$(( $ret | $? ))
		fi
	done
	shopt -u nullglob
	return $ret
}

eqatag() {
	__eqatag "${@}"
}

if [ -n "${MISC_FUNCTIONS_ARGS}" ]; then
	__source_all_bashrcs
	[ "$PORTAGE_DEBUG" == "1" ] && set -x
	for x in ${MISC_FUNCTIONS_ARGS}; do
		${x}
	done
	unset x
	[[ -n $PORTAGE_EBUILD_EXIT_FILE ]] && > "$PORTAGE_EBUILD_EXIT_FILE"
	if [[ -n $PORTAGE_IPC_DAEMON ]] ; then
		[[ ! -s $SANDBOX_LOG ]]
		"$PORTAGE_BIN_PATH"/ebuild-ipc exit $?
	fi
fi

:
