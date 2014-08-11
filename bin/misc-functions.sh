#!/bin/bash
# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
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
	local f i qa_var x
	if ! ___eapi_has_prefix_variables; then
		local EPREFIX= ED=${D}
	fi

	cd "${ED}" || die "cd failed"

	qa_var="QA_FLAGS_IGNORED_${ARCH/-/_}"
	eval "[[ -n \${!qa_var} ]] && QA_FLAGS_IGNORED=(\"\${${qa_var}[@]}\")"
	if [[ ${#QA_FLAGS_IGNORED[@]} -eq 1 ]] ; then
		local shopts=$-
		set -o noglob
		QA_FLAGS_IGNORED=(${QA_FLAGS_IGNORED})
		set +o noglob
		set -${shopts}
	fi

	# Check for files built without respecting *FLAGS. Note that
	# -frecord-gcc-switches must be in all *FLAGS variables, in
	# order to avoid false positive results here.
	# NOTE: This check must execute before prepall/prepstrip, since
	# prepstrip strips the .GCC.command.line sections.
	if type -P scanelf > /dev/null && ! has binchecks ${RESTRICT} && \
		[[ "${CFLAGS}" == *-frecord-gcc-switches* ]] && \
		[[ "${CXXFLAGS}" == *-frecord-gcc-switches* ]] && \
		[[ "${FFLAGS}" == *-frecord-gcc-switches* ]] && \
		[[ "${FCFLAGS}" == *-frecord-gcc-switches* ]] ; then
		rm -f "${T}"/scanelf-ignored-CFLAGS.log
		for x in $(scanelf -qyRF '#k%p' -k '!.GCC.command.line' "${ED}") ; do
			# Separate out file types that are known to support
			# .GCC.command.line sections, using the `file` command
			# similar to how prepstrip uses it.
			f=$(file "${x}") || continue
			[[ -z ${f} ]] && continue
			if [[ ${f} == *"SB executable"* ||
				${f} == *"SB shared object"* ]] ; then
				echo "${x}" >> "${T}"/scanelf-ignored-CFLAGS.log
			fi
		done

		if [[ -f "${T}"/scanelf-ignored-CFLAGS.log ]] ; then

			if [ "${QA_STRICT_FLAGS_IGNORED-unset}" = unset ] ; then
				for x in "${QA_FLAGS_IGNORED[@]}" ; do
					sed -e "s#^${x#/}\$##" -i "${T}"/scanelf-ignored-CFLAGS.log
				done
			fi
			# Filter anything under /usr/lib/debug/ in order to avoid
			# duplicate warnings for splitdebug files.
			sed -e "s#^usr/lib/debug/.*##" -e "/^\$/d" -e "s#^#/#" \
				-i "${T}"/scanelf-ignored-CFLAGS.log
			f=$(<"${T}"/scanelf-ignored-CFLAGS.log)
			if [[ -n ${f} ]] ; then
				__vecho -ne '\n'
				eqawarn "${BAD}QA Notice: Files built without respecting CFLAGS have been detected${NORMAL}"
				eqawarn " Please include the following list of files in your report:"
				eqawarn "${f}"
				__vecho -ne '\n'
				sleep 1
			else
				rm -f "${T}"/scanelf-ignored-CFLAGS.log
			fi
		fi
	fi

	export STRIP_MASK
	prepall
	___eapi_has_docompress && prepcompress
	ecompressdir --dequeue
	ecompress --dequeue

	# Prefix specific checks
	[[ ${ED} != ${D} ]] && install_qa_check_prefix

	f=
	for x in etc/app-defaults usr/man usr/info usr/X11R6 usr/doc usr/locale ; do
		[[ -d ${ED}/$x ]] && f+="  $x\n"
	done
	if [[ -n $f ]] ; then
		eqawarn "QA Notice: This ebuild installs into the following deprecated directories:"
		eqawarn
		eqawarn "$f"
	fi

	# It's ok create these directories, but not to install into them. #493154
	# TODO: We should add var/lib to this list.
	f=
	for x in var/cache var/lock var/run run ; do
		if [[ ! -L ${ED}/${x} && -d ${ED}/${x} ]] ; then
			if [[ -z $(find "${ED}/${x}" -prune -empty) ]] ; then
				f+=$(cd "${ED}"; find "${x}" -printf '  %p\n')
			fi
		fi
	done
	if [[ -n ${f} ]] ; then
		eqawarn "QA Notice: This ebuild installs into paths that should be created at runtime."
		eqawarn " To fix, simply do not install into these directories.  Instead, your package"
		eqawarn " should create dirs on the fly at runtime as needed via init scripts/etc..."
		eqawarn
		eqawarn "${f}"
	fi

	set +f
	f=
	for x in "${ED}etc/udev/rules.d/"* "${ED}lib"*"/udev/rules.d/"* ; do
		[[ -e ${x} ]] || continue
		[[ ${x} == ${ED}lib/udev/rules.d/* ]] && continue
		f+="  ${x#${ED}}\n"
	done
	if [[ -n $f ]] ; then
		eqawarn "QA Notice: udev rules should be installed in /lib/udev/rules.d:"
		eqawarn
		eqawarn "$f"
	fi

	# Now we look for all world writable files.
	local unsafe_files=$(find "${ED}" -type f -perm -2 | sed -e "s:^${ED}:- :")
	if [[ -n ${unsafe_files} ]] ; then
		__vecho "QA Security Notice: world writable file(s):"
		__vecho "${unsafe_files}"
		__vecho "- This may or may not be a security problem, most of the time it is one."
		__vecho "- Please double check that $PF really needs a world writeable bit and file bugs accordingly."
		sleep 1
	fi

	if type -P scanelf > /dev/null && ! has binchecks ${RESTRICT}; then
		local insecure_rpath=0 tmp_quiet=${PORTAGE_QUIET}
		local x

		# display warnings when using stricter because we die afterwards
		if has stricter ${FEATURES} ; then
			unset PORTAGE_QUIET
		fi

		# Make sure we disallow insecure RUNPATH/RPATHs.
		#   1) References to PORTAGE_BUILDDIR are banned because it's a
		#      security risk. We don't want to load files from a
		#      temporary directory.
		#   2) If ROOT != "/", references to ROOT are banned because
		#      that directory won't exist on the target system.
		#   3) Null paths are banned because the loader will search $PWD when
		#      it finds null paths.
		local forbidden_dirs="${PORTAGE_BUILDDIR}"
		if [[ -n "${ROOT}" && "${ROOT}" != "/" ]]; then
			forbidden_dirs+=" ${ROOT}"
		fi
		local dir l rpath_files=$(scanelf -F '%F:%r' -qBR "${ED}")
		f=""
		for dir in ${forbidden_dirs}; do
			for l in $(echo "${rpath_files}" | grep -E ":${dir}|::|: "); do
				f+="  ${l%%:*}\n"
				if ! has stricter ${FEATURES}; then
					__vecho "Auto fixing rpaths for ${l%%:*}"
					TMPDIR="${dir}" scanelf -BXr "${l%%:*}" -o /dev/null
				fi
			done
		done

		# Reject set*id binaries with $ORIGIN in RPATH #260331
		x=$(
			find "${ED}" -type f \( -perm -u+s -o -perm -g+s \) -print0 | \
			xargs -0 scanelf -qyRF '%r %p' | grep '$ORIGIN'
		)

		# Print QA notice.
		if [[ -n ${f}${x} ]] ; then
			__vecho -ne '\n'
			eqawarn "QA Notice: The following files contain insecure RUNPATHs"
			eqawarn " Please file a bug about this at http://bugs.gentoo.org/"
			eqawarn " with the maintaining herd of the package."
			eqawarn "${f}${f:+${x:+\n}}${x}"
			__vecho -ne '\n'
			if [[ -n ${x} ]] || has stricter ${FEATURES} ; then
				insecure_rpath=1
			fi
		fi

		# TEXTRELs are baaaaaaaad
		# Allow devs to mark things as ignorable ... e.g. things that are
		# binary-only and upstream isn't cooperating (nvidia-glx) ... we
		# allow ebuild authors to set QA_TEXTRELS_arch and QA_TEXTRELS ...
		# the former overrides the latter ... regexes allowed ! :)
		qa_var="QA_TEXTRELS_${ARCH/-/_}"
		[[ -n ${!qa_var} ]] && QA_TEXTRELS=${!qa_var}
		[[ -n ${QA_STRICT_TEXTRELS} ]] && QA_TEXTRELS=""
		export QA_TEXTRELS="${QA_TEXTRELS} lib*/modules/*.ko"
		f=$(scanelf -qyRF '%t %p' "${ED}" | grep -v 'usr/lib/debug/')
		if [[ -n ${f} ]] ; then
			scanelf -qyRAF '%T %p' "${PORTAGE_BUILDDIR}"/ &> "${T}"/scanelf-textrel.log
			__vecho -ne '\n'
			eqawarn "QA Notice: The following files contain runtime text relocations"
			eqawarn " Text relocations force the dynamic linker to perform extra"
			eqawarn " work at startup, waste system resources, and may pose a security"
			eqawarn " risk.  On some architectures, the code may not even function"
			eqawarn " properly, if at all."
			eqawarn " For more information, see http://hardened.gentoo.org/pic-fix-guide.xml"
			eqawarn " Please include the following list of files in your report:"
			eqawarn "${f}"
			__vecho -ne '\n'
			die_msg="${die_msg} textrels,"
			sleep 1
		fi

		# Also, executable stacks only matter on linux (and just glibc atm ...)
		f=""
		case ${CTARGET:-${CHOST}} in
			*-linux-gnu*)
			# Check for files with executable stacks, but only on arches which
			# are supported at the moment.  Keep this list in sync with
			# http://www.gentoo.org/proj/en/hardened/gnu-stack.xml (Arch Status)
			case ${CTARGET:-${CHOST}} in
				arm*|i?86*|ia64*|m68k*|s390*|sh*|x86_64*)
					# Allow devs to mark things as ignorable ... e.g. things
					# that are binary-only and upstream isn't cooperating ...
					# we allow ebuild authors to set QA_EXECSTACK_arch and
					# QA_EXECSTACK ... the former overrides the latter ...
					# regexes allowed ! :)

					qa_var="QA_EXECSTACK_${ARCH/-/_}"
					[[ -n ${!qa_var} ]] && QA_EXECSTACK=${!qa_var}
					[[ -n ${QA_STRICT_EXECSTACK} ]] && QA_EXECSTACK=""
					qa_var="QA_WX_LOAD_${ARCH/-/_}"
					[[ -n ${!qa_var} ]] && QA_WX_LOAD=${!qa_var}
					[[ -n ${QA_STRICT_WX_LOAD} ]] && QA_WX_LOAD=""
					export QA_EXECSTACK="${QA_EXECSTACK} lib*/modules/*.ko"
					export QA_WX_LOAD="${QA_WX_LOAD} lib*/modules/*.ko"
					f=$(scanelf -qyRAF '%e %p' "${ED}" | grep -v 'usr/lib/debug/')
					;;
			esac
			;;
		esac
		if [[ -n ${f} ]] ; then
			# One more pass to help devs track down the source
			scanelf -qyRAF '%e %p' "${PORTAGE_BUILDDIR}"/ &> "${T}"/scanelf-execstack.log
			__vecho -ne '\n'
			eqawarn "QA Notice: The following files contain writable and executable sections"
			eqawarn " Files with such sections will not work properly (or at all!) on some"
			eqawarn " architectures/operating systems.  A bug should be filed at"
			eqawarn " http://bugs.gentoo.org/ to make sure the issue is fixed."
			eqawarn " For more information, see http://hardened.gentoo.org/gnu-stack.xml"
			eqawarn " Please include the following list of files in your report:"
			eqawarn " Note: Bugs should be filed for the respective maintainers"
			eqawarn " of the package in question and not hardened@g.o."
			eqawarn "${f}"
			__vecho -ne '\n'
			die_msg="${die_msg} execstacks"
			sleep 1
		fi

		# Check for files built without respecting LDFLAGS
		if [[ "${LDFLAGS}" == *,--hash-style=gnu* ]] && \
			! has binchecks ${RESTRICT} ; then
			f=$(scanelf -qyRF '#k%p' -k .hash "${ED}")
			if [[ -n ${f} ]] ; then
				echo "${f}" > "${T}"/scanelf-ignored-LDFLAGS.log
				if [ "${QA_STRICT_FLAGS_IGNORED-unset}" = unset ] ; then
					for x in "${QA_FLAGS_IGNORED[@]}" ; do
						sed -e "s#^${x#/}\$##" -i "${T}"/scanelf-ignored-LDFLAGS.log
					done
				fi
				# Filter anything under /usr/lib/debug/ in order to avoid
				# duplicate warnings for splitdebug files.
				sed -e "s#^usr/lib/debug/.*##" -e "/^\$/d" -e "s#^#/#" \
					-i "${T}"/scanelf-ignored-LDFLAGS.log
				f=$(<"${T}"/scanelf-ignored-LDFLAGS.log)
				if [[ -n ${f} ]] ; then
					__vecho -ne '\n'
					eqawarn "${BAD}QA Notice: Files built without respecting LDFLAGS have been detected${NORMAL}"
					eqawarn " Please include the following list of files in your report:"
					eqawarn "${f}"
					__vecho -ne '\n'
					sleep 1
				else
					rm -f "${T}"/scanelf-ignored-LDFLAGS.log
				fi
			fi
		fi

		if [[ ${insecure_rpath} -eq 1 ]] ; then
			die "Aborting due to serious QA concerns with RUNPATH/RPATH"
		elif [[ -n ${die_msg} ]] && has stricter ${FEATURES} ; then
			die "Aborting due to QA concerns: ${die_msg}"
		fi

		# Check for shared libraries lacking SONAMEs
		qa_var="QA_SONAME_${ARCH/-/_}"
		eval "[[ -n \${!qa_var} ]] && QA_SONAME=(\"\${${qa_var}[@]}\")"
		f=$(scanelf -ByF '%S %p' "${ED}"{,usr/}lib*/lib*.so* | awk '$2 == "" { print }' | sed -e "s:^[[:space:]]${ED}:/:")
		if [[ -n ${f} ]] ; then
			echo "${f}" > "${T}"/scanelf-missing-SONAME.log
			if [[ "${QA_STRICT_SONAME-unset}" == unset ]] ; then
				if [[ ${#QA_SONAME[@]} -gt 1 ]] ; then
					for x in "${QA_SONAME[@]}" ; do
						sed -e "s#^/${x#/}\$##" -i "${T}"/scanelf-missing-SONAME.log
					done
				else
					local shopts=$-
					set -o noglob
					for x in ${QA_SONAME} ; do
						sed -e "s#^/${x#/}\$##" -i "${T}"/scanelf-missing-SONAME.log
					done
					set +o noglob
					set -${shopts}
				fi
			fi
			sed -e "/^\$/d" -i "${T}"/scanelf-missing-SONAME.log
			f=$(<"${T}"/scanelf-missing-SONAME.log)
			if [[ -n ${f} ]] ; then
				__vecho -ne '\n'
				eqawarn "QA Notice: The following shared libraries lack a SONAME"
				eqawarn "${f}"
				__vecho -ne '\n'
				sleep 1
			else
				rm -f "${T}"/scanelf-missing-SONAME.log
			fi
		fi

		# Check for shared libraries lacking NEEDED entries
		qa_var="QA_DT_NEEDED_${ARCH/-/_}"
		eval "[[ -n \${!qa_var} ]] && QA_DT_NEEDED=(\"\${${qa_var}[@]}\")"
		f=$(scanelf -ByF '%n %p' "${ED}"{,usr/}lib*/lib*.so* | awk '$2 == "" { print }' | sed -e "s:^[[:space:]]${ED}:/:")
		if [[ -n ${f} ]] ; then
			echo "${f}" > "${T}"/scanelf-missing-NEEDED.log
			if [[ "${QA_STRICT_DT_NEEDED-unset}" == unset ]] ; then
				if [[ ${#QA_DT_NEEDED[@]} -gt 1 ]] ; then
					for x in "${QA_DT_NEEDED[@]}" ; do
						sed -e "s#^/${x#/}\$##" -i "${T}"/scanelf-missing-NEEDED.log
					done
				else
					local shopts=$-
					set -o noglob
					for x in ${QA_DT_NEEDED} ; do
						sed -e "s#^/${x#/}\$##" -i "${T}"/scanelf-missing-NEEDED.log
					done
					set +o noglob
					set -${shopts}
				fi
			fi
			sed -e "/^\$/d" -i "${T}"/scanelf-missing-NEEDED.log
			f=$(<"${T}"/scanelf-missing-NEEDED.log)
			if [[ -n ${f} ]] ; then
				__vecho -ne '\n'
				eqawarn "QA Notice: The following shared libraries lack NEEDED entries"
				eqawarn "${f}"
				__vecho -ne '\n'
				sleep 1
			else
				rm -f "${T}"/scanelf-missing-NEEDED.log
			fi
		fi

		PORTAGE_QUIET=${tmp_quiet}
	fi

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

	local unsafe_files=$(find "${ED}" -type f '(' -perm -2002 -o -perm -4002 ')' | sed -e "s:^${ED}:/:")
	if [[ -n ${unsafe_files} ]] ; then
		eqawarn "QA Notice: Unsafe files detected (set*id and world writable)"
		eqawarn "${unsafe_files}"
		die "Unsafe files found in \${D}.  Portage will not install them."
	fi

	if [[ -d ${D%/}${D} ]] ; then
		local -i INSTALLTOD=0
		while read -r -d $'\0' i ; do
			eqawarn "QA Notice: /${i##${D%/}${D}} installed in \${D}/\${D}"
			((INSTALLTOD++))
		done < <(find "${D%/}${D}" -print0)
		die "Aborting due to QA concerns: ${INSTALLTOD} files installed in ${D%/}${D}"
	fi

	# Sanity check syntax errors in init.d scripts
	local d
	for d in /etc/conf.d /etc/init.d ; do
		[[ -d ${ED}/${d} ]] || continue
		for i in "${ED}"/${d}/* ; do
			[[ -L ${i} ]] && continue
			# if empty conf.d/init.d dir exists (baselayout), then i will be "/etc/conf.d/*" and not exist
			[[ ! -e ${i} ]] && continue
			if [[ ${d} == /etc/init.d && ${i} != *.sh ]] ; then
				# skip non-shell-script for bug #451386
				[[ $(head -n1 "${i}") =~ ^#!.*[[:space:]/](runscript|sh)$ ]] || continue
			fi
			bash -n "${i}" || die "The init.d file has syntax errors: ${i}"
		done
	done

	local checkbashisms=$(type -P checkbashisms)
	if [[ -n ${checkbashisms} ]] ; then
		for d in /etc/init.d ; do
			[[ -d ${ED}${d} ]] || continue
			for i in "${ED}${d}"/* ; do
				[[ -e ${i} ]] || continue
				[[ -L ${i} ]] && continue
				f=$("${checkbashisms}" -f "${i}" 2>&1)
				[[ $? != 0 && -n ${f} ]] || continue
				eqawarn "QA Notice: shell script appears to use non-POSIX feature(s):"
				while read -r ;
					do eqawarn "   ${REPLY}"
				done <<< "${f//${ED}}"
			done
		done
	fi

	# Look for leaking LDFLAGS into pkg-config files
	f=$(egrep -sH '^Libs.*-Wl,(-O[012]|--hash-style)' "${ED}"/usr/*/pkgconfig/*.pc)
	if [[ -n ${f} ]] ; then
		eqawarn "QA Notice: pkg-config files with wrong LDFLAGS detected:"
		eqawarn "${f//${D}}"
	fi

	# this should help to ensure that all (most?) shared libraries are executable
	# and that all libtool scripts / static libraries are not executable
	local j
	for i in "${ED}"opt/*/lib* \
	         "${ED}"lib* \
	         "${ED}"usr/lib* ; do
		[[ ! -d ${i} ]] && continue

		for j in "${i}"/*.so.* "${i}"/*.so ; do
			[[ ! -e ${j} ]] && continue
			[[ -L ${j} ]] && continue
			[[ -x ${j} ]] && continue
			__vecho "making executable: ${j#${ED}}"
			chmod +x "${j}"
		done

		for j in "${i}"/*.a "${i}"/*.la ; do
			[[ ! -e ${j} ]] && continue
			[[ -L ${j} ]] && continue
			[[ ! -x ${j} ]] && continue
			__vecho "removing executable bit: ${j#${ED}}"
			chmod -x "${j}"
		done

		for j in "${i}"/*.{a,dll,dylib,sl,so}.* "${i}"/*.{a,dll,dylib,sl,so} ; do
			[[ ! -e ${j} ]] && continue
			[[ ! -L ${j} ]] && continue
			linkdest=$(readlink "${j}")
			if [[ ${linkdest} == /* ]] ; then
				__vecho -ne '\n'
				eqawarn "QA Notice: Found an absolute symlink in a library directory:"
				eqawarn "           ${j#${D}} -> ${linkdest}"
				eqawarn "           It should be a relative symlink if in the same directory"
				eqawarn "           or a linker script if it crosses the /usr boundary."
			fi
		done
	done

	# When installing static libraries into /usr/lib and shared libraries into
	# /lib, we have to make sure we have a linker script in /usr/lib along side
	# the static library, or gcc will utilize the static lib when linking :(.
	# http://bugs.gentoo.org/4411
	abort="no"
	local a s
	for a in "${ED}"usr/lib*/*.a ; do
		s=${a%.a}.so
		if [[ ! -e ${s} ]] ; then
			s=${s%usr/*}${s##*/usr/}
			if [[ -e ${s} ]] ; then
				__vecho -ne '\n'
				eqawarn "QA Notice: Missing gen_usr_ldscript for ${s##*/}"
	 			abort="yes"
			fi
		fi
	done
	[[ ${abort} == "yes" ]] && die "add those ldscripts"

	# Make sure people don't store libtool files or static libs in /lib
	f=$(ls "${ED}"lib*/*.{a,la} 2>/dev/null)
	if [[ -n ${f} ]] ; then
		__vecho -ne '\n'
		eqawarn "QA Notice: Excessive files found in the / partition"
		eqawarn "${f}"
		__vecho -ne '\n'
		die "static archives (*.a) and libtool library files (*.la) belong in /usr/lib*, not /lib*"
	fi

	# Verify that the libtool files don't contain bogus $D entries.
	local abort=no gentoo_bug=no always_overflow=no
	for a in "${ED}"usr/lib*/*.la ; do
		s=${a##*/}
		if grep -qs "${ED}" "${a}" ; then
			__vecho -ne '\n'
			eqawarn "QA Notice: ${s} appears to contain PORTAGE_TMPDIR paths"
			abort="yes"
		fi
	done
	[[ ${abort} == "yes" ]] && die "soiled libtool library files found"

	# Evaluate misc gcc warnings
	if [[ -n ${PORTAGE_LOG_FILE} && -r ${PORTAGE_LOG_FILE} ]] ; then
		# In debug mode, this variable definition and corresponding grep calls
		# will produce false positives if they're shown in the trace.
		local reset_debug=0
		if [[ ${-/x/} != $- ]] ; then
			set +x
			reset_debug=1
		fi
		local m msgs=(
			": warning: dereferencing type-punned pointer will break strict-aliasing rules"
			": warning: dereferencing pointer .* does break strict-aliasing rules"
			": warning: implicit declaration of function"
			": warning: incompatible implicit declaration of built-in function"
			": warning: is used uninitialized in this function" # we'll ignore "may" and "might"
			": warning: comparisons like X<=Y<=Z do not have their mathematical meaning"
			": warning: null argument where non-null required"
			": warning: array subscript is below array bounds"
			": warning: array subscript is above array bounds"
			": warning: attempt to free a non-heap object"
			": warning: .* called with .*bigger.* than .* destination buffer"
			": warning: call to .* will always overflow destination buffer"
			": warning: assuming pointer wraparound does not occur when comparing"
			": warning: hex escape sequence out of range"
			": warning: [^ ]*-hand operand of comma .*has no effect"
			": warning: converting to non-pointer type .* from NULL"
			": warning: NULL used in arithmetic"
			": warning: passing NULL to non-pointer argument"
			": warning: the address of [^ ]* will always evaluate as"
			": warning: the address of [^ ]* will never be NULL"
			": warning: too few arguments for format"
			": warning: reference to local variable .* returned"
			": warning: returning reference to temporary"
			": warning: function returns address of local variable"
			": warning: .*\\[-Wsizeof-pointer-memaccess\\]"
			": warning: .*\\[-Waggressive-loop-optimizations\\]"
			# this may be valid code :/
			#": warning: multi-character character constant"
			# need to check these two ...
			#": warning: assuming signed overflow does not occur when"
			#": warning: comparison with string literal results in unspecified behav"
			# yacc/lex likes to trigger this one
			#": warning: extra tokens at end of .* directive"
			# only gcc itself triggers this ?
			#": warning: .*noreturn.* function does return"
			# these throw false positives when 0 is used instead of NULL
			#": warning: missing sentinel in function call"
			#": warning: not enough variable arguments to fit a sentinel"
		)
		abort="no"
		i=0
		local grep_cmd=grep
		[[ $PORTAGE_LOG_FILE = *.gz ]] && grep_cmd=zgrep
		while [[ -n ${msgs[${i}]} ]] ; do
			m=${msgs[$((i++))]}
			# force C locale to work around slow unicode locales #160234
			f=$(LC_ALL=C $grep_cmd "${m}" "${PORTAGE_LOG_FILE}")
			if [[ -n ${f} ]] ; then
				abort="yes"
				# for now, don't make this fatal (see bug #337031)
				#case "$m" in
				#	": warning: call to .* will always overflow destination buffer") always_overflow=yes ;;
				#esac
				if [[ $always_overflow = yes ]] ; then
					eerror
					eerror "QA Notice: Package triggers severe warnings which indicate that it"
					eerror "           may exhibit random runtime failures."
					eerror
					eerror "${f}"
					eerror
					eerror " Please file a bug about this at http://bugs.gentoo.org/"
					eerror " with the maintaining herd of the package."
					eerror
				else
					__vecho -ne '\n'
					eqawarn "QA Notice: Package triggers severe warnings which indicate that it"
					eqawarn "           may exhibit random runtime failures."
					eqawarn "${f}"
					__vecho -ne '\n'
				fi
			fi
		done
		local cat_cmd=cat
		[[ $PORTAGE_LOG_FILE = *.gz ]] && cat_cmd=zcat
		[[ $reset_debug = 1 ]] && set -x
		# Use safe cwd, avoiding unsafe import for bug #469338.
		f=$(cd "${PORTAGE_PYM_PATH}" ; $cat_cmd "${PORTAGE_LOG_FILE}" | \
			"${PORTAGE_PYTHON:-/usr/bin/python}" "$PORTAGE_BIN_PATH"/check-implicit-pointer-usage.py || die "check-implicit-pointer-usage.py failed")
		if [[ -n ${f} ]] ; then

			# In the future this will be a forced "die". In preparation,
			# increase the log level from "qa" to "eerror" so that people
			# are aware this is a problem that must be fixed asap.

			# just warn on 32bit hosts but bail on 64bit hosts
			case ${CHOST} in
				alpha*|hppa64*|ia64*|powerpc64*|mips64*|sparc64*|sparcv9*|x86_64*) gentoo_bug=yes ;;
			esac

			abort=yes

			if [[ $gentoo_bug = yes ]] ; then
				eerror
				eerror "QA Notice: Package triggers severe warnings which indicate that it"
				eerror "           will almost certainly crash on 64bit architectures."
				eerror
				eerror "${f}"
				eerror
				eerror " Please file a bug about this at http://bugs.gentoo.org/"
				eerror " with the maintaining herd of the package."
				eerror
			else
				__vecho -ne '\n'
				eqawarn "QA Notice: Package triggers severe warnings which indicate that it"
				eqawarn "           will almost certainly crash on 64bit architectures."
				eqawarn "${f}"
				__vecho -ne '\n'
			fi

		fi
		if [[ ${abort} == "yes" ]] ; then
			if [[ $gentoo_bug = yes || $always_overflow = yes ]] ; then
				die "install aborted due to severe warnings shown above"
			else
				echo "Please do not file a Gentoo bug and instead" \
				"report the above QA issues directly to the upstream" \
				"developers of this software." | fmt -w 70 | \
				while read -r line ; do eqawarn "${line}" ; done
				eqawarn "Homepage: ${HOMEPAGE}"
				has stricter ${FEATURES} && \
					die "install aborted due to severe warnings shown above"
			fi
		fi
	fi

	# Portage regenerates this on the installed system.
	rm -f "${ED}"/usr/share/info/dir{,.gz,.bz2} || die "rm failed!"

	if has multilib-strict ${FEATURES} && \
	   [[ -x /usr/bin/file && -x /usr/bin/find ]] && \
	   [[ -n ${MULTILIB_STRICT_DIRS} && -n ${MULTILIB_STRICT_DENY} ]]
	then
		rm -f "${T}/multilib-strict.log"
		local abort=no dir file
		MULTILIB_STRICT_EXEMPT=$(echo ${MULTILIB_STRICT_EXEMPT} | sed -e 's:\([(|)]\):\\\1:g')
		for dir in ${MULTILIB_STRICT_DIRS} ; do
			[[ -d ${ED}/${dir} ]] || continue
			for file in $(find ${ED}/${dir} -type f | grep -v "^${ED}/${dir}/${MULTILIB_STRICT_EXEMPT}"); do
				if file ${file} | egrep -q "${MULTILIB_STRICT_DENY}" ; then
					echo "${file#${ED}//}" >> "${T}/multilib-strict.log"
				fi
			done
		done

		if [[ -s ${T}/multilib-strict.log ]] ; then
			if [[ ${#QA_MULTILIB_PATHS[@]} -eq 1 ]] ; then
				local shopts=$-
				set -o noglob
				QA_MULTILIB_PATHS=(${QA_MULTILIB_PATHS})
				set +o noglob
				set -${shopts}
			fi
			if [ "${QA_STRICT_MULTILIB_PATHS-unset}" = unset ] ; then
				for x in "${QA_MULTILIB_PATHS[@]}" ; do
					sed -e "s#^${x#/}\$##" -i "${T}/multilib-strict.log"
				done
				sed -e "/^\$/d" -i "${T}/multilib-strict.log"
			fi
			if [[ -s ${T}/multilib-strict.log ]] ; then
				abort=yes
				echo "Files matching a file type that is not allowed:"
				while read -r ; do
					echo "   ${REPLY}"
				done < "${T}/multilib-strict.log"
			fi
		fi

		[[ ${abort} == yes ]] && die "multilib-strict check failed!"
	fi

	local pngfix=$(type -P pngfix)
	if [[ -n ${pngfix} ]] ; then
		local pngout=()
		local next

		while read -r -a pngout ; do
			local error

			case "${pngout[1]}" in
				CHK)
					error='invalid checksum'
					;;
				TFB)
					error='broken IDAT window length'
					;;
			esac

			if [[ -n ${error} ]] ; then
				if [[ -z ${next} ]] ; then
					eqawarn "QA Notice: broken .png files found:"
					next=1
				fi
				eqawarn "   ${pngout[@]:7}: ${error}"
			fi
		done < <(find "${ED}" -type f -name '*.png' -exec "${pngfix}" {} +)
	fi
}

install_qa_check_prefix() {
	if [[ -d ${ED}/${D} ]] ; then
		find "${ED}/${D}" | \
		while read i ; do
			eqawarn "QA Notice: /${i##${ED}/${D}} installed in \${ED}/\${D}"
		done
		die "Aborting due to QA concerns: files installed in ${ED}/${D}"
	fi

	if [[ -d ${ED}/${EPREFIX} ]] ; then
		find "${ED}/${EPREFIX}/" | \
		while read i ; do
			eqawarn "QA Notice: ${i#${D}} double prefix"
		done
		die "Aborting due to QA concerns: double prefix files installed"
	fi

	if [[ -d ${D} ]] ; then
		INSTALLTOD=$(find ${D%/} | egrep -v "^${ED}" | sed -e "s|^${D%/}||" | awk '{if (length($0) <= length("'"${EPREFIX}"'")) { if (substr("'"${EPREFIX}"'", 1, length($0)) != $0) {print $0;} } else if (substr($0, 1, length("'"${EPREFIX}"'")) != "'"${EPREFIX}"'") {print $0;} }')
		if [[ -n ${INSTALLTOD} ]] ; then
			eqawarn "QA Notice: the following files are outside of the prefix:"
			eqawarn "${INSTALLTOD}"
			die "Aborting due to QA concerns: there are files installed outside the prefix"
		fi
	fi

	# all further checks rely on ${ED} existing
	[[ -d ${ED} ]] || return

	# check shebangs, bug #282539
	rm -f "${T}"/non-prefix-shebangs-errs
	local WHITELIST=" /usr/bin/env "
	# this is hell expensive, but how else?
	find "${ED}" -executable \! -type d -print0 \
			| xargs -0 grep -H -n -m1 "^#!" \
			| while read f ;
	do
		local fn=${f%%:*}
		local pos=${f#*:} ; pos=${pos%:*}
		local line=${f##*:}
		# shebang always appears on the first line ;)
		[[ ${pos} != 1 ]] && continue
		local oldIFS=${IFS}
		IFS=$'\r'$'\n'$'\t'" "
		line=( ${line#"#!"} )
		IFS=${oldIFS}
		[[ ${WHITELIST} == *" ${line[0]} "* ]] && continue
		local fp=${fn#${D}} ; fp=/${fp%/*}
		# line[0] can be an absolutised path, bug #342929
		local eprefix=$(canonicalize ${EPREFIX})
		local rf=${fn}
		# in case we deal with a symlink, make sure we don't replace it
		# with a real file (sed -i does that)
		if [[ -L ${fn} ]] ; then
			rf=$(readlink ${fn})
			[[ ${rf} != /* ]] && rf=${fn%/*}/${rf}
			# ignore symlinks pointing to outside prefix
			# as seen in sys-devel/native-cctools
			[[ $(canonicalize "/${rf#${D}}") != ${eprefix}/* ]] && continue
		fi
		# does the shebang start with ${EPREFIX}, and does it exist?
		if [[ ${line[0]} == ${EPREFIX}/* || ${line[0]} == ${eprefix}/* ]] ; then
			if [[ ! -e ${ROOT%/}${line[0]} && ! -e ${D%/}${line[0]} ]] ; then
				# hmm, refers explicitly to $EPREFIX, but doesn't exist,
				# if it's in PATH that's wrong in any case
				if [[ ":${PATH}:" == *":${fp}:"* ]] ; then
					echo "${fn#${D}}:${line[0]} (explicit EPREFIX but target not found)" \
						>> "${T}"/non-prefix-shebangs-errs
				else
					eqawarn "${fn#${D}} has explicit EPREFIX in shebang but target not found (${line[0]})"
				fi
			fi
			continue
		fi
		# unprefixed shebang, is the script directly in $PATH?
		if [[ ":${PATH}:" == *":${fp}:"* ]] ; then
			if [[ -e ${EROOT}${line[0]} || -e ${ED}${line[0]} ]] ; then
				# is it unprefixed, but we can just fix it because a
				# prefixed variant exists
				eqawarn "prefixing shebang of ${fn#${D}}"
				# statement is made idempotent on purpose, because
				# symlinks may point to the same target, and hence the
				# same real file may be sedded multiple times since we
				# read the shebangs in one go upfront for performance
				# reasons
				sed -i -e '1s:^#! \?'"${line[0]}"':#!'"${EPREFIX}"${line[0]}':' "${rf}"
				continue
			else
				# this is definitely wrong: script in $PATH and invalid shebang
				echo "${fn#${D}}:${line[0]} (script ${fn##*/} installed in PATH but interpreter ${line[0]} not found)" \
					>> "${T}"/non-prefix-shebangs-errs
			fi
		else
			# unprefixed/invalid shebang, but outside $PATH, this may be
			# intended (e.g. config.guess) so remain silent by default
			has stricter ${FEATURES} && \
				eqawarn "invalid shebang in ${fn#${D}}: ${line[0]}"
		fi
	done
	if [[ -e "${T}"/non-prefix-shebangs-errs ]] ; then
		eqawarn "QA Notice: the following files use invalid (possible non-prefixed) shebangs:"
		while read line ; do
			eqawarn "  ${line}"
		done < "${T}"/non-prefix-shebangs-errs
		rm -f "${T}"/non-prefix-shebangs-errs
		die "Aborting due to QA concerns: invalid shebangs found"
	fi
}

install_mask() {
	local root="$1"
	shift
	local install_mask="$*"

	# we don't want globbing for initial expansion, but afterwards, we do
	local shopts=$-
	set -o noglob
	local no_inst
	for no_inst in ${install_mask}; do
		set +o noglob
		__quiet_mode || einfo "Removing ${no_inst}"
		# normal stuff
		rm -Rf "${root}"/${no_inst} >&/dev/null

		# we also need to handle globs (*.a, *.h, etc)
		find "${root}" \( -path "${no_inst}" -or -name "${no_inst}" \) \
			-exec rm -fR {} \; >/dev/null 2>&1
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
					for x in 5 4 3 2 1 0; do sleep 0.25 ; done
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

				/usr/sbin/setfiles "${file_contexts_path}" -r "${D}" "${D}"
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

	cd "${T}"

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
	tar $tar_options -cf - $PORTAGE_BINPKG_TAR_OPTS -C "${PROOT}" . | \
		$PORTAGE_BZIP2_COMMAND -c > "$PORTAGE_BINPKG_TMPFILE"
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
