#!/bin/bash
# Copyright 1999-2014 Gentoo Foundation
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

prepcompress() {
	local -a include exclude incl_d incl_f
	local f g i real_f real_d
	if ! ___eapi_has_prefix_variables; then
		local ED=${D}
	fi

	# Canonicalize path names and check for their existence.
	real_d=$(canonicalize "${ED}")
	for (( i = 0; i < ${#PORTAGE_DOCOMPRESS[@]}; i++ )); do
		real_f=$(canonicalize "${ED}${PORTAGE_DOCOMPRESS[i]}")
		f=${real_f#"${real_d}"}
		if [[ ${real_f} != "${f}" ]] && [[ -d ${real_f} || -f ${real_f} ]]
		then
			include[${#include[@]}]=${f:-/}
		elif [[ ${i} -ge 3 ]]; then
			ewarn "prepcompress:" \
				"ignoring nonexistent path '${PORTAGE_DOCOMPRESS[i]}'"
		fi
	done
	for (( i = 0; i < ${#PORTAGE_DOCOMPRESS_SKIP[@]}; i++ )); do
		real_f=$(canonicalize "${ED}${PORTAGE_DOCOMPRESS_SKIP[i]}")
		f=${real_f#"${real_d}"}
		if [[ ${real_f} != "${f}" ]] && [[ -d ${real_f} || -f ${real_f} ]]
		then
			exclude[${#exclude[@]}]=${f:-/}
		elif [[ ${i} -ge 1 ]]; then
			ewarn "prepcompress:" \
				"ignoring nonexistent path '${PORTAGE_DOCOMPRESS_SKIP[i]}'"
		fi
	done

	# Remove redundant entries from lists.
	# For the include list, remove any entries that are:
	# a) contained in a directory in the include or exclude lists, or
	# b) identical with an entry in the exclude list.
	for (( i = ${#include[@]} - 1; i >= 0; i-- )); do
		f=${include[i]}
		for g in "${include[@]}"; do
			if [[ ${f} == "${g%/}"/* ]]; then
				unset include[i]
				continue 2
			fi
		done
		for g in "${exclude[@]}"; do
			if [[ ${f} = "${g}" || ${f} == "${g%/}"/* ]]; then
				unset include[i]
				continue 2
			fi
		done
	done
	# For the exclude list, remove any entries that are:
	# a) contained in a directory in the exclude list, or
	# b) _not_ contained in a directory in the include list.
	for (( i = ${#exclude[@]} - 1; i >= 0; i-- )); do
		f=${exclude[i]}
		for g in "${exclude[@]}"; do
			if [[ ${f} == "${g%/}"/* ]]; then
				unset exclude[i]
				continue 2
			fi
		done
		for g in "${include[@]}"; do
			[[ ${f} == "${g%/}"/* ]] && continue 2
		done
		unset exclude[i]
	done

	# Split the include list into directories and files
	for f in "${include[@]}"; do
		if [[ -d ${ED}${f} ]]; then
			incl_d[${#incl_d[@]}]=${f}
		else
			incl_f[${#incl_f[@]}]=${f}
		fi
	done

	# Queue up for compression.
	# ecompress{,dir} doesn't like to be called with empty argument lists.
	[[ ${#incl_d[@]} -gt 0 ]] && ecompressdir --limit ${PORTAGE_DOCOMPRESS_SIZE_LIMIT:-0} --queue "${incl_d[@]}"
	[[ ${#incl_f[@]} -gt 0 ]] && ecompress --queue "${incl_f[@]/#/${ED}}"
	[[ ${#exclude[@]} -gt 0 ]] && ecompressdir --ignore "${exclude[@]}"
	return 0
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

	export STRIP_MASK
	prepall
	___eapi_has_docompress && prepcompress
	ecompressdir --dequeue
	ecompress --dequeue

	# Create NEEDED.ELF.2 regardless of RESTRICT=binchecks, since this info is
	# too useful not to have (it's required for things like preserve-libs), and
	# it's tempting for ebuild authors to set RESTRICT=binchecks for packages
	# containing pre-built binaries.
	if type -P scanelf > /dev/null ; then
		# Save NEEDED information after removing self-contained providers
		rm -f "$PORTAGE_BUILDDIR"/build-info/NEEDED{,.ELF.2}
		scanelf -qyRF '%a;%p;%S;%r;%n' "${D}" | { while IFS= read -r l; do
			arch=${l%%;*}; l=${l#*;}
			obj="/${l%%;*}"; l=${l#*;}
			soname=${l%%;*}; l=${l#*;}
			rpath=${l%%;*}; l=${l#*;}; [ "${rpath}" = "  -  " ] && rpath=""
			needed=${l%%;*}; l=${l#*;}
			echo "${obj} ${needed}"	>> "${PORTAGE_BUILDDIR}"/build-info/NEEDED
			echo "${arch:3};${obj};${soname};${rpath};${needed}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED.ELF.2
		done }

		[ -n "${QA_SONAME_NO_SYMLINK}" ] && \
			echo "${QA_SONAME_NO_SYMLINK}" > \
			"${PORTAGE_BUILDDIR}"/build-info/QA_SONAME_NO_SYMLINK

		if has binchecks ${RESTRICT} && \
			[ -s "${PORTAGE_BUILDDIR}/build-info/NEEDED.ELF.2" ] ; then
			eqawarn "QA Notice: RESTRICT=binchecks prevented checks on these ELF files:"
			eqawarn "$(while read -r x; do x=${x#*;} ; x=${x%%;*} ; echo "${x#${EPREFIX}}" ; done < "${PORTAGE_BUILDDIR}"/build-info/NEEDED.ELF.2)"
		fi
	fi

	# Portage regenerates this on the installed system.
	rm -f "${ED}"/usr/share/info/dir{,.gz,.bz2} || die "rm failed!"
}

postinst_qa_check() {
	local d f paths qa_checks=()
	if ! ___eapi_has_prefix_variables; then
		local EPREFIX= EROOT=${ROOT}
	fi

	cd "${EROOT}" || die "cd failed"

	# Collect the paths for QA checks, highest prio first.
	paths=(
		# sysadmin overrides
		"${PORTAGE_OVERRIDE_EPREFIX}"/usr/local/lib/postinst-qa-check.d
		# system-wide package installs
		"${PORTAGE_OVERRIDE_EPREFIX}"/usr/lib/postinst-qa-check.d
	)

	# Now repo-specific checks.
	# (yes, PORTAGE_ECLASS_LOCATIONS contains repo paths...)
	for d in "${PORTAGE_ECLASS_LOCATIONS[@]}"; do
		paths+=(
			"${d}"/metadata/postinst-qa-check.d
		)
	done

	paths+=(
		# Portage built-in checks
		"${PORTAGE_OVERRIDE_EPREFIX}"/usr/lib/portage/postinst-qa-check.d
		"${PORTAGE_BIN_PATH}"/postinst-qa-check.d
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
			source "${d}/${f}" || eerror "Post-postinst QA check ${f} failed to run"
		)
	done < <(printf "%s\0" "${qa_checks[@]}" | LC_ALL=C sort -u -z)
}

install_mask() {
	local root="$1"
	shift
	local install_mask="$*"

	# We think of $install_mask as a space-separated list of
	# globs. We don't want globbing in the "for" loop; that is, we
	# want to keep the asterisks in the indivual entries.
	local shopts=$-
	set -o noglob
	local no_inst
	for no_inst in ${install_mask}; do
		# Here, $no_inst is a single "entry" potentially
		# containing a glob. From now on, we *do* want to
		# expand it.
		set +o noglob

		# The standard case where $no_inst is something that
		# the shell could expand on its own.
		if [[ -e "${root}"/${no_inst} || -L "${root}"/${no_inst} ||
			"${root}"/${no_inst} != $(echo "${root}"/${no_inst}) ]] ; then
			__quiet_mode || einfo "Removing ${no_inst}"
			rm -Rf "${root}"/${no_inst} >&/dev/null
		fi

		# We also want to allow the user to specify a "bare
		# glob." For example, $no_inst="*.a" should prevent
		# ALL files ending in ".a" from being installed,
		# regardless of their location/depth. We achieve this
		# by passing the pattern to `find`.
		find "${root}" \( -path "${no_inst}" -or -name "${no_inst}" \) \
			-print0 2> /dev/null \
		| LC_ALL=C sort -z \
		| while read -r -d ''; do
			__quiet_mode || einfo "Removing /${REPLY#${root}}"
			rm -Rf "${REPLY}" >&/dev/null
		done

	done
	# set everything back the way we found it
	set +o noglob
	set -${shopts}
}

preinst_mask() {
	if [ -z "${D}" ]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi

	if ! ___eapi_has_prefix_variables; then
		local ED=${D}
	fi

	# Make sure $PWD is not ${D} so that we don't leave gmon.out files
	# in there in case any tools were built with -pg in CFLAGS.
	cd "${T}"

	# remove man pages, info pages, docs if requested
	local f
	for f in man info doc; do
		if has no${f} $FEATURES; then
			INSTALL_MASK="${INSTALL_MASK} /usr/share/${f}"
		fi
	done

	install_mask "${ED}" "${INSTALL_MASK}"

	# remove share dir if unnessesary
	if has nodoc $FEATURES || has noman $FEATURES || has noinfo $FEATURES; then
		rmdir "${ED}usr/share" &> /dev/null
	fi
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
				ebegin ">>> SetUID and SetGID: [chmod o-r] /${i#${ED}}"
				chmod o-r "$i"
				eend $?
			else
				ebegin ">>> SetUID: [chmod go-r] /${i#${ED}}"
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
				ebegin ">>> SetGID: [chmod o-r] /${i#${ED}}"
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
				install_path=/${i#${ED}}
				if grep -q "^${install_path}\$" "${sfconf}" ; then
					__vecho "- ${install_path} is an approved suid file"
				else
					__vecho ">>> Removing sbit on non registered ${install_path}"
					LC_ALL=C sleep 1.5
					ls_ret=$(ls -ldh "${i}")
					chmod ugo-s "${i}"
					grep "^#${install_path}$" "${sfconf}" > /dev/null || {
						__vecho ">>> Appending commented out entry to ${sfconf} for ${PF}"
						echo "## ${ls_ret%${ED}*}${install_path}" >> "${sfconf}"
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
		if [ -f /selinux/context -o -f /sys/fs/selinux/context ] && \
			[ -x /usr/sbin/setfiles -a -x /usr/sbin/selinuxconfig ]; then
			__vecho ">>> Setting SELinux security labels"
			(
				eval "$(/usr/sbin/selinuxconfig)" || \
					die "Failed to determine SELinux policy paths.";

				addwrite /selinux/context
				addwrite /sys/fs/selinux/context

				/usr/sbin/setfiles -F "${file_contexts_path}" -r "${D}" "${D}"
			) || die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			__vecho "!!! Unable to set SELinux security labels"
		fi
	fi
}

__dyn_package() {
	local PROOT

	if ! ___eapi_has_prefix_variables; then
		local EPREFIX= ED=${D}
	fi

	# Make sure $PWD is not ${D} so that we don't leave gmon.out files
	# in there in case any tools were built with -pg in CFLAGS.

	cd "${T}" || die

	if [[ -n ${PKG_INSTALL_MASK} ]] ; then
		PROOT=${T}/packaging/
		# make a temporary copy of ${D} so that any modifications we do that
		# are binpkg specific, do not influence the actual installed image.
		rm -rf "${PROOT}" || die "failed removing stale package tree"
		cp -pPR $(cp --help | grep -qs -e-l && echo -l) \
			"${D}" "${PROOT}" \
			|| die "failed creating packaging tree"

		install_mask "${PROOT%/}${EPREFIX}/" "${PKG_INSTALL_MASK}"
	else
		PROOT=${D}
	fi

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
	tar $tar_options -cf - $PORTAGE_BINPKG_TAR_OPTS -C "${PROOT}" . | \
		$PORTAGE_COMPRESSION_COMMAND -c > "$PORTAGE_BINPKG_TMPFILE"
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

	# cleanup our temp tree
	[[ -n ${PKG_INSTALL_MASK} ]] && rm -rf "${PROOT}"
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
