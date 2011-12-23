#!@PORTAGE_BASH@
# Copyright 1999-2011 Gentoo Foundation
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

source "${PORTAGE_BIN_PATH:-@PORTAGE_BASE@/bin}/ebuild.sh"

install_symlink_html_docs() {
	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local ED=${D} ;; esac
	# PREFIX LOCAL: ED needs not to exist, whereas D does
	[[ ! -d ${ED} && -d ${D} ]] && dodir /
	# END PREFIX LOCAL
	cd "${ED}" || die "cd failed"
	#symlink the html documentation (if DOC_SYMLINKS_DIR is set in make.conf)
	if [ -n "${DOC_SYMLINKS_DIR}" ] ; then
		local mydocdir docdir
		for docdir in "${HTMLDOC_DIR:-does/not/exist}" "${PF}/html" "${PF}/HTML" "${P}/html" "${P}/HTML" ; do
			if [ -d "usr/share/doc/${docdir}" ] ; then
				mydocdir="${EPREFIX}/usr/share/doc/${docdir}"
			fi
		done
		if [ -n "${mydocdir}" ] ; then
			local mysympath
			if [ -z "${SLOT}" -o "${SLOT}" = "0" ] ; then
				mysympath="${DOC_SYMLINKS_DIR}/${CATEGORY}/${PN}"
			else
				mysympath="${DOC_SYMLINKS_DIR}/${CATEGORY}/${PN}-${SLOT}"
			fi
			einfo "Symlinking ${mysympath} to the HTML documentation"
			dodir "${DOC_SYMLINKS_DIR}/${CATEGORY}"
			dosym "${mydocdir}" "${mysympath}"
		fi
	fi
}

# replacement for "readlink -f" or "realpath"
canonicalize() {
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
	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local ED=${D} ;; esac

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
	[[ ${#incl_d[@]} -gt 0 ]] && ecompressdir --queue "${incl_d[@]}"
	[[ ${#incl_f[@]} -gt 0 ]] && ecompress --queue "${incl_f[@]/#/${ED}}"
	[[ ${#exclude[@]} -gt 0 ]] && ecompressdir --ignore "${exclude[@]}"
	return 0
}

install_qa_check() {
	local f i x
	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local ED=${D} ;; esac

	# PREFIX LOCAL: ED needs not to exist, whereas D does
	cd "${D}" || die "cd failed"
	# END PREFIX LOCAL

	export STRIP_MASK
	prepall
	has "${EAPI}" 0 1 2 3 || prepcompress
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

	# Now we look for all world writable files.
	local unsafe_files=$(find "${ED}" -type f -perm -2 | sed -e "s:^${ED}:- :")
	if [[ -n ${unsafe_files} ]] ; then
		vecho "QA Security Notice: world writable file(s):"
		vecho "${unsafe_files}"
		vecho "- This may or may not be a security problem, most of the time it is one."
		vecho "- Please double check that $PF really needs a world writeable bit and file bugs accordingly."
		sleep 1
	fi

	# PREFIX LOCAL:
	# anything outside the prefix should be caught by the Prefix QA
	# check, so if there's nothing in ED, we skip searching for QA
	# checks there, the specific QA funcs can hence rely on ED existing
	if [[ -d ${ED} ]] ; then
		case ${CHOST} in
			*-darwin*)
				# Mach-O platforms (NeXT, Darwin, OSX)
				install_qa_check_macho
			;;
			*-interix*|*-winnt*)
				# PECOFF platforms (Windows/Interix)
				install_qa_check_pecoff
			;;
			*-aix*)
				# XCOFF platforms (AIX)
				install_qa_check_xcoff
			;;
			*)
				# because this is the majority: ELF platforms (Linux,
				# Solaris, *BSD, IRIX, etc.)
				install_qa_check_elf
			;;
		esac
	fi

	# this is basically here such that the diff with trunk remains just
	# offsetted and not out of order
	install_qa_check_misc
	# END PREFIX LOCAL
}

install_qa_check_elf() {
	if type -P scanelf > /dev/null && ! has binchecks ${RESTRICT}; then
		local qa_var insecure_rpath=0 tmp_quiet=${PORTAGE_QUIET}
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
					vecho "Auto fixing rpaths for ${l%%:*}"
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
			vecho -ne '\n'
			eqawarn "QA Notice: The following files contain insecure RUNPATHs"
			eqawarn " Please file a bug about this at http://bugs.gentoo.org/"
			eqawarn " with the maintaining herd of the package."
			eqawarn "${f}${f:+${x:+\n}}${x}"
			vecho -ne '\n'
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
			vecho -ne '\n'
			eqawarn "QA Notice: The following files contain runtime text relocations"
			eqawarn " Text relocations force the dynamic linker to perform extra"
			eqawarn " work at startup, waste system resources, and may pose a security"
			eqawarn " risk.  On some architectures, the code may not even function"
			eqawarn " properly, if at all."
			eqawarn " For more information, see http://hardened.gentoo.org/pic-fix-guide.xml"
			eqawarn " Please include the following list of files in your report:"
			eqawarn "${f}"
			vecho -ne '\n'
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
			vecho -ne '\n'
			eqawarn "QA Notice: The following files contain writable and executable sections"
			eqawarn " Files with such sections will not work properly (or at all!) on some"
			eqawarn " architectures/operating systems.  A bug should be filed at"
			eqawarn " http://bugs.gentoo.org/ to make sure the issue is fixed."
			eqawarn " For more information, see http://hardened.gentoo.org/gnu-stack.xml"
			eqawarn " Please include the following list of files in your report:"
			eqawarn " Note: Bugs should be filed for the respective maintainers"
			eqawarn " of the package in question and not hardened@g.o."
			eqawarn "${f}"
			vecho -ne '\n'
			die_msg="${die_msg} execstacks"
			sleep 1
		fi

		# Merge QA_FLAGS_IGNORED and QA_DT_HASH into a single array, since
		# QA_DT_HASH is deprecated.
		qa_var="QA_FLAGS_IGNORED_${ARCH/-/_}"
		eval "[[ -n \${!qa_var} ]] && QA_FLAGS_IGNORED=(\"\${${qa_var}[@]}\")"
		if [[ ${#QA_FLAGS_IGNORED[@]} -eq 1 ]] ; then
			local shopts=$-
			set -o noglob
			QA_FLAGS_IGNORED=(${QA_FLAGS_IGNORED})
			set +o noglob
			set -${shopts}
		fi

		qa_var="QA_DT_HASH_${ARCH/-/_}"
		eval "[[ -n \${!qa_var} ]] && QA_DT_HASH=(\"\${${qa_var}[@]}\")"
		if [[ ${#QA_DT_HASH[@]} -eq 1 ]] ; then
			local shopts=$-
			set -o noglob
			QA_DT_HASH=(${QA_DT_HASH})
			set +o noglob
			set -${shopts}
		fi

		if [[ -n ${QA_DT_HASH} ]] ; then
			QA_FLAGS_IGNORED=("${QA_FLAGS_IGNORED[@]}" "${QA_DT_HASH[@]}")
			unset QA_DT_HASH
		fi

		# Merge QA_STRICT_FLAGS_IGNORED and QA_STRICT_DT_HASH, since
		# QA_STRICT_DT_HASH is deprecated
		if [ "${QA_STRICT_FLAGS_IGNORED-unset}" = unset ] && \
			[ "${QA_STRICT_DT_HASH-unset}" != unset ] ; then
			QA_STRICT_FLAGS_IGNORED=1
			unset QA_STRICT_DT_HASH
		fi

		# Check for files built without respecting *FLAGS. Note that
		# -frecord-gcc-switches must be in all *FLAGS variables, in
		# order to avoid false positive results here.
		if [[ "${CFLAGS}" == *-frecord-gcc-switches* ]] && \
			[[ "${CXXFLAGS}" == *-frecord-gcc-switches* ]] && \
			[[ "${FFLAGS}" == *-frecord-gcc-switches* ]] && \
			[[ "${FCFLAGS}" == *-frecord-gcc-switches* ]] && \
			! has binchecks ${RESTRICT} ; then
			f=$(scanelf -qyRF '%k %p' -k \!.GCC.command.line "${ED}" | sed -e "s:\!.GCC.command.line ::")
			if [[ -n ${f} ]] ; then
				echo "${f}" > "${T}"/scanelf-ignored-CFLAGS.log
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
					vecho -ne '\n'
					eqawarn "${BAD}QA Notice: Files built without respecting CFLAGS have been detected${NORMAL}"
					eqawarn " Please include the following list of files in your report:"
					eqawarn "${f}"
					vecho -ne '\n'
					sleep 1
				else
					rm -f "${T}"/scanelf-ignored-CFLAGS.log
				fi
			fi
		fi

		# Check for files built without respecting LDFLAGS
		if [[ "${LDFLAGS}" == *,--hash-style=gnu* ]] && \
			! has binchecks ${RESTRICT} ; then 
			f=$(scanelf -qyRF '%k %p' -k .hash "${ED}" | sed -e "s:\.hash ::")
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
					vecho -ne '\n'
					eqawarn "${BAD}QA Notice: Files built without respecting LDFLAGS have been detected${NORMAL}"
					eqawarn " Please include the following list of files in your report:"
					eqawarn "${f}"
					vecho -ne '\n'
					sleep 1
				else
					rm -f "${T}"/scanelf-ignored-LDFLAGS.log
				fi
			fi
		fi

		# Save NEEDED information after removing self-contained providers
		rm -f "$PORTAGE_BUILDDIR"/build-info/NEEDED{,.ELF.2}
		scanelf -qyRF '%a;%p;%S;%r;%n' "${D}" | { while IFS= read -r l; do
			arch=${l%%;*}; l=${l#*;}
			obj="/${l%%;*}"; l=${l#*;}
			soname=${l%%;*}; l=${l#*;}
			rpath=${l%%;*}; l=${l#*;}; [ "${rpath}" = "  -  " ] && rpath=""
			needed=${l%%;*}; l=${l#*;}
			if [ -z "${rpath}" -o -n "${rpath//*ORIGIN*}" ]; then
				# object doesn't contain $ORIGIN in its runpath attribute
				echo "${obj} ${needed}"	>> "${PORTAGE_BUILDDIR}"/build-info/NEEDED
				echo "${arch:3};${obj};${soname};${rpath};${needed}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED.ELF.2
			else
				dir=${obj%/*}
				# replace $ORIGIN with the dirname of the current object for the lookup
				opath=$(echo :${rpath}: | sed -e "s#.*:\(.*\)\$ORIGIN\(.*\):.*#\1${dir}\2#")
				sneeded=$(echo ${needed} | tr , ' ')
				rneeded=""
				for lib in ${sneeded}; do
					found=0
					for path in ${opath//:/ }; do
						[ -e "${D}/${path}/${lib}" ] && found=1 && break
					done
					[ "${found}" -eq 0 ] && rneeded="${rneeded},${lib}"
				done
				rneeded=${rneeded:1}
				if [ -n "${rneeded}" ]; then
					echo "${obj} ${rneeded}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED
					echo "${arch:3};${obj};${soname};${rpath};${rneeded}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED.ELF.2
				fi
			fi
		done }

		[ -n "${QA_SONAME_NO_SYMLINK}" ] && \
			echo "${QA_SONAME_NO_SYMLINK}" > \
			"${PORTAGE_BUILDDIR}"/build-info/QA_SONAME_NO_SYMLINK

		if [[ ${insecure_rpath} -eq 1 ]] ; then
			die "Aborting due to serious QA concerns with RUNPATH/RPATH"
		elif [[ -n ${die_msg} ]] && has stricter ${FEATURES} ; then
			die "Aborting due to QA concerns: ${die_msg}"
		fi

		# Check for shared libraries lacking SONAMEs
		qa_var="QA_SONAME_${ARCH/-/_}"
		eval "[[ -n \${!qa_var} ]] && QA_SONAME=(\"\${${qa_var}[@]}\")"
		f=$(scanelf -ByF '%S %p' "${ED}"{,usr/}lib*/lib*.so* | gawk '$2 == "" { print }' | sed -e "s:^[[:space:]]${ED}:/:")
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
				vecho -ne '\n'
				eqawarn "QA Notice: The following shared libraries lack a SONAME"
				eqawarn "${f}"
				vecho -ne '\n'
				sleep 1
			else
				rm -f "${T}"/scanelf-missing-SONAME.log
			fi
		fi

		# Check for shared libraries lacking NEEDED entries
		qa_var="QA_DT_NEEDED_${ARCH/-/_}"
		eval "[[ -n \${!qa_var} ]] && QA_DT_NEEDED=(\"\${${qa_var}[@]}\")"
		# PREFIX LOCAL: keep offset prefix in the recorded files
		f=$(scanelf -ByF '%n %p' "${ED}"{,usr/}lib*/lib*.so* | gawk '$2 == "" { print }' | sed -e "s:^[[:space:]]${D}:/:")
		# END PREFIX LOCAL
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
				vecho -ne '\n'
				eqawarn "QA Notice: The following shared libraries lack NEEDED entries"
				eqawarn "${f}"
				vecho -ne '\n'
				sleep 1
			else
				rm -f "${T}"/scanelf-missing-NEEDED.log
			fi
		fi

		PORTAGE_QUIET=${tmp_quiet}
	fi
}

install_qa_check_misc() {
	# PREFIX LOCAL: keep offset prefix in the reported files
	local unsafe_files=$(find "${ED}" -type f '(' -perm -2002 -o -perm -4002 ')' | sed -e "s:^${D}:/:")
	# END PREFIX LOCAL
	if [[ -n ${unsafe_files} ]] ; then
		eqawarn "QA Notice: Unsafe files detected (set*id and world writable)"
		eqawarn "${unsafe_files}"
		die "Unsafe files found in \${D}.  Portage will not install them."
	fi

	if [[ -d ${D}/${D} ]] ; then
		find "${D}/${D}" | \
		while read i ; do
			eqawarn "QA Notice: /${i##${D}/${D}} installed in \${D}/\${D}"
		done
		die "Aborting due to QA concerns: files installed in ${D}/${D}"
	fi

	# Sanity check syntax errors in init.d scripts
	local d
	for d in /etc/conf.d /etc/init.d ; do
		[[ -d ${ED}/${d} ]] || continue
		for i in "${ED}"/${d}/* ; do
			[[ -L ${i} ]] && continue
			# if empty conf.d/init.d dir exists (baselayout), then i will be "/etc/conf.d/*" and not exist
			[[ ! -e ${i} ]] && continue
			bash -n "${i}" || die "The init.d file has syntax errors: ${i}"
		done
	done

	# this should help to ensure that all (most?) shared libraries are executable
	# and that all libtool scripts / static libraries are not executable
	local j
	for i in "${ED}"opt/*/lib{,32,64} \
	         "${ED}"lib{,32,64}       \
	         "${ED}"usr/lib{,32,64}   \
	         "${ED}"usr/X11R6/lib{,32,64} ; do
		[[ ! -d ${i} ]] && continue

		for j in "${i}"/*.so.* "${i}"/*.so "${i}"/*.dylib "${i}"/*.dll ; do
			[[ ! -e ${j} ]] && continue
			[[ -L ${j} ]] && continue
			[[ -x ${j} ]] && continue
			vecho "making executable: ${j#${ED}}"
			chmod +x "${j}"
		done

		for j in "${i}"/*.a "${i}"/*.la ; do
			[[ ! -e ${j} ]] && continue
			[[ -L ${j} ]] && continue
			[[ ! -x ${j} ]] && continue
			vecho "removing executable bit: ${j#${ED}}"
			chmod -x "${j}"
		done

		for j in "${i}"/*.{a,dll,dylib,sl,so}.* "${i}"/*.{a,dll,dylib,sl,so} ; do
			[[ ! -e ${j} ]] && continue
			[[ ! -L ${j} ]] && continue
			linkdest=$(readlink "${j}")
			if [[ ${linkdest} == /* ]] ; then
				vecho -ne '\n'
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
		# PREFIX LOCAL: support MachO objects
		[[ ${CHOST} == *-darwin* ]] \
			&& s=${a%.a}.dylib \
			|| s=${a%.a}.so
		# END PREFIX LOCAL
		if [[ ! -e ${s} ]] ; then
			s=${s%usr/*}${s##*/usr/}
			if [[ -e ${s} ]] ; then
				vecho -ne '\n'
				eqawarn "QA Notice: Missing gen_usr_ldscript for ${s##*/}"
	 			abort="yes"
			fi
		fi
	done
	[[ ${abort} == "yes" ]] && die "add those ldscripts"

	# Make sure people don't store libtool files or static libs in /lib
	# PREFIX LOCAL: on AIX, "dynamic libs" have extension .a, so don't
	# get false positives
	[[ ${CHOST} == *-aix* ]] \
		&& f=$(ls "${ED}"lib*/*.la 2>/dev/null || true) \
		|| f=$(ls "${ED}"lib*/*.{a,la} 2>/dev/null)
	# END PREFIX LOCAL
	if [[ -n ${f} ]] ; then
		vecho -ne '\n'
		eqawarn "QA Notice: Excessive files found in the / partition"
		eqawarn "${f}"
		vecho -ne '\n'
		die "static archives (*.a) and libtool library files (*.la) do not belong in /"
	fi

	# Verify that the libtool files don't contain bogus $D entries.
	local abort=no gentoo_bug=no always_overflow=no
	for a in "${ED}"usr/lib*/*.la ; do
		s=${a##*/}
		if grep -qs "${ED}" "${a}" ; then
			vecho -ne '\n'
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
					vecho -ne '\n'
					eqawarn "QA Notice: Package triggers severe warnings which indicate that it"
					eqawarn "           may exhibit random runtime failures."
					eqawarn "${f}"
					vecho -ne '\n'
				fi
			fi
		done
		local cat_cmd=cat
		[[ $PORTAGE_LOG_FILE = *.gz ]] && cat_cmd=zcat
		[[ $reset_debug = 1 ]] && set -x
		f=$($cat_cmd "${PORTAGE_LOG_FILE}" | \
			"${PORTAGE_PYTHON:-@PREFIX_PORTAGE_PYTHON@}" "$PORTAGE_BIN_PATH"/check-implicit-pointer-usage.py || die "check-implicit-pointer-usage.py failed")
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
				vecho -ne '\n'
				eqawarn "QA Notice: Package triggers severe warnings which indicate that it"
				eqawarn "           will almost certainly crash on 64bit architectures."
				eqawarn "${f}"
				vecho -ne '\n'
			fi

		fi
		if [[ ${abort} == "yes" ]] ; then
			if [[ $gentoo_bug = yes || $always_overflow = yes ]] ; then
				die "install aborted due to" \
					"severe warnings shown above"
			else
				echo "Please do not file a Gentoo bug and instead" \
				"report the above QA issues directly to the upstream" \
				"developers of this software." | fmt -w 70 | \
				while read -r line ; do eqawarn "${line}" ; done
				eqawarn "Homepage: ${HOMEPAGE}"
				has stricter ${FEATURES} && die "install aborted due to" \
					"severe warnings shown above"
			fi
		fi
	fi

	# Portage regenerates this on the installed system.
	rm -f "${ED}"/usr/share/info/dir{,.gz,.bz2}

	if has multilib-strict ${FEATURES} && \
	   [[ -x ${EPREFIX}/usr/bin/file && -x ${EPREFIX}/usr/bin/find ]] && \
	   [[ -n ${MULTILIB_STRICT_DIRS} && -n ${MULTILIB_STRICT_DENY} ]]
	then
		local abort=no dir file firstrun=yes
		MULTILIB_STRICT_EXEMPT=$(echo ${MULTILIB_STRICT_EXEMPT} | sed -e 's:\([(|)]\):\\\1:g')
		for dir in ${MULTILIB_STRICT_DIRS} ; do
			[[ -d ${ED}/${dir} ]] || continue
			for file in $(find ${ED}/${dir} -type f | grep -v "^${ED}/${dir}/${MULTILIB_STRICT_EXEMPT}"); do
				if file ${file} | egrep -q "${MULTILIB_STRICT_DENY}" ; then
					if [[ ${firstrun} == yes ]] ; then
						echo "Files matching a file type that is not allowed:"
						firstrun=no
					fi
					abort=yes
					echo "   ${file#${ED}//}"
				fi
			done
		done
		[[ ${abort} == yes ]] && die "multilib-strict check failed!"
	fi

	# ensure packages don't install systemd units automagically
	if ! has systemd ${INHERITED} && \
		[[ -d "${ED}"/lib/systemd/system ]]
	then
		eqawarn "QA Notice: package installs systemd unit files (/lib/systemd/system)"
		eqawarn "           but does not inherit systemd.eclass."
		has stricter ${FEATURES} \
			&& die "install aborted due to missing inherit of systemd.eclass"
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

	# this does not really belong here, but it's closely tied to
	# the code below; many runscripts generate positives here, and we
	# know they don't work (bug #196294) so as long as that one
	# remains an issue, simply remove them as they won't work
	# anyway, avoid etc/init.d/functions.sh from being thrown away
	if [[ ( -d "${ED}"/etc/conf.d || -d "${ED}"/etc/init.d ) && ! -f "${ED}"/etc/init.d/functions.sh ]] ; then
		ewarn "removed /etc/init.d and /etc/conf.d directories until bug #196294 has been resolved"
		rm -Rf "${ED}"/etc/{conf,init}.d
	fi

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

install_qa_check_macho() {
	if ! has binchecks ${RESTRICT} ; then
		# on Darwin, dynamic libraries are called .dylibs instead of
		# .sos.  In addition the version component is before the
		# extension, not after it.  Check for this, and *only* warn
		# about it.  Some packages do ship .so files on Darwin and make
		# it work (ugly!).
		rm -f "${T}/mach-o.check"
		find ${ED%/} -name "*.so" -or -name "*.so.*" | \
		while read i ; do
			[[ $(file $i) == *"Mach-O"* ]] && \
				echo "${i#${D}}" >> "${T}/mach-o.check"
		done
		if [[ -f ${T}/mach-o.check ]] ; then
			f=$(< "${T}/mach-o.check")
			vecho -ne '\a\n'
			eqawarn "QA Notice: Found .so dynamic libraries on Darwin:"
			eqawarn "    ${f//$'\n'/\n    }"
		fi
		rm -f "${T}/mach-o.check"

		# The naming for dynamic libraries is different on Darwin; the
		# version component is before the extention, instead of after
		# it, as with .sos.  Again, make this a warning only.
		rm -f "${T}/mach-o.check"
		find ${ED%/} -name "*.dylib.*" | \
		while read i ; do
			echo "${i#${D}}" >> "${T}/mach-o.check"
		done
		if [[ -f "${T}/mach-o.check" ]] ; then
			f=$(< "${T}/mach-o.check")
			vecho -ne '\a\n'
			eqawarn "QA Notice: Found wrongly named dynamic libraries on Darwin:"
			eqawarn "    ${f// /\n    }"
		fi
		rm -f "${T}/mach-o.check"
	fi

	# While we generate the NEEDED files, check that we don't get kernel
	# traps at runtime because of broken install_names on Darwin.
	rm -f "${T}"/.install_name_check_failed
	scanmacho -qyRF '%a;%p;%S;%n' "${D}" | { while IFS= read l ; do
		arch=${l%%;*}; l=${l#*;}
		obj="/${l%%;*}"; l=${l#*;}
		install_name=${l%%;*}; l=${l#*;}
		needed=${l%%;*}; l=${l#*;}

		# See if the self-reference install_name points to an existing
		# and to be installed file.  This usually is a symlink for the
		# major version.
		if [[ ! -e ${D}${install_name} ]] ; then
			eqawarn "QA Notice: invalid self-reference install_name ${install_name} in ${obj}"
			# remember we are in an implicit subshell, that's
			# why we touch a file here ... ideally we should be
			# able to die correctly/nicely here
			touch "${T}"/.install_name_check_failed
		fi

		# this is ugly, paths with spaces won't work
		reevaluate=0
		for lib in ${needed//,/ } ; do
			if [[ ${lib} == ${D}* ]] ; then
				eqawarn "QA Notice: install_name references \${D}: ${lib} in ${obj}"
				touch "${T}"/.install_name_check_failed
			elif [[ ${lib} == ${S}* ]] ; then
				eqawarn "QA Notice: install_name references \${S}: ${lib} in ${obj}"
				touch "${T}"/.install_name_check_failed
			elif [[ ! -e ${lib} && ! -e ${D}${lib} && ${lib} != "@executable_path/"* && ${lib} != "@loader_path/"* ]] ; then
				# try to "repair" this if possible, happens because of
				# gen_usr_ldscript tactics
				s=${lib%usr/*}${lib##*/usr/}
				if [[ -e ${D}${s} ]] ; then
					ewarn "correcting install_name from ${lib} to ${s} in ${obj}"
					install_name_tool -change \
						"${lib}" "${s}" "${D}${obj}"
					reevaluate=1
				else
					eqawarn "QA Notice: invalid reference to ${lib} in ${obj}"
					# remember we are in an implicit subshell, that's
					# why we touch a file here ... ideally we should be
					# able to die correctly/nicely here
					touch "${T}"/.install_name_check_failed
				fi
			fi
		done
		if [[ ${reevaluate} == 1 ]]; then
			# install_name(s) have been changed, refresh data so we
			# store the correct meta data
			l=$(scanmacho -qyF '%a;%p;%S;%n' ${D}${obj})
			arch=${l%%;*}; l=${l#*;}
			obj="/${l%%;*}"; l=${l#*;}
			install_name=${l%%;*}; l=${l#*;}
			needed=${l%%;*}; l=${l#*;}
		fi

		# backwards compatability
		echo "${obj} ${needed}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED
		# what we use
		echo "${arch};${obj};${install_name};${needed}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED.MACHO.3
	done }
	if [[ -f ${T}/.install_name_check_failed ]] ; then
		# secret switch "allow_broken_install_names" to get
		# around this and install broken crap (not a good idea)
		has allow_broken_install_names ${FEATURES} || \
			die "invalid install_name found, your application or library will crash at runtime"
	fi
}

install_qa_check_pecoff() {
	local _pfx_scan="readpecoff ${CHOST}"

	# this one uses readpecoff, which supports multiple prefix platforms!
	# this is absolutely _not_ optimized for speed, and there may be plenty
	# of possibilities by introducing one or the other cache!
	if ! has binchecks ${RESTRICT}; then
		# copied and adapted from the above scanelf code.
		local qa_var insecure_rpath=0 tmp_quiet=${PORTAGE_QUIET}
		local f x

		# display warnings when using stricter because we die afterwards
		if has stricter ${FEATURES} ; then
			unset PORTAGE_QUIET
		fi

		local _exec_find_opt="-executable"
		[[ ${CHOST} == *-winnt* ]] && _exec_find_opt='-name *.dll -o -name *.exe'

		# Make sure we disallow insecure RUNPATH/RPATH's
		# Don't want paths that point to the tree where the package was built
		# (older, broken libtools would do this).  Also check for null paths
		# because the loader will search $PWD when it finds null paths.

		f=$(
			find "${ED}" -type f '(' ${_exec_find_opt} ')' -print0 | xargs -0 ${_pfx_scan} | \
			while IFS=";" read arch obj soname rpath needed ; do \
			echo "${rpath}" | grep -E "(${PORTAGE_BUILDDIR}|: |::|^:|^ )" > /dev/null 2>&1 \
				&& echo "${obj}"; done;
		)
		# Reject set*id binaries with $ORIGIN in RPATH #260331
		x=$(
			find "${ED}" -type f '(' -perm -u+s -o -perm -g+s ')' -print0 | \
			xargs -0 ${_pfx_scan} | while IFS=";" read arch obj soname rpath needed; do \
			echo "${rpath}" | grep '$ORIGIN' > /dev/null 2>&1 && echo "${obj}"; done;
		)
		if [[ -n ${f}${x} ]] ; then
			vecho -ne '\a\n'
			eqawarn "QA Notice: The following files contain insecure RUNPATH's"
			eqawarn " Please file a bug about this at http://bugs.gentoo.org/"
			eqawarn " with the maintaining herd of the package."
			eqawarn "${f}${f:+${x:+\n}}${x}"
			vecho -ne '\a\n'
			if [[ -n ${x} ]] || has stricter ${FEATURES} ; then
				insecure_rpath=1
			else
				eqawarn "cannot automatically fix runpaths on interix platforms!"
			fi
		fi

		rm -f "${PORTAGE_BUILDDIR}"/build-info/NEEDED
		rm -f "${PORTAGE_BUILDDIR}"/build-info/NEEDED.PECOFF.1

		# Save NEEDED information after removing self-contained providers
		find "${ED}" -type f '(' ${_exec_find_opt} ')' -print0 | xargs -0 ${_pfx_scan} | { while IFS=';' read arch obj soname rpath needed; do
			# need to strip image dir from object name.
			obj="/${obj#${D}}"
			if [ -z "${rpath}" -o -n "${rpath//*ORIGIN*}" ]; then
				# object doesn't contain $ORIGIN in its runpath attribute
				echo "${obj} ${needed}"	>> "${PORTAGE_BUILDDIR}"/build-info/NEEDED
				echo "${arch};${obj};${soname};${rpath};${needed}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED.PECOFF.1
			else
				dir=${obj%/*}
				# replace $ORIGIN with the dirname of the current object for the lookup
				opath=$(echo :${rpath}: | sed -e "s#.*:\(.*\)\$ORIGIN\(.*\):.*#\1${dir}\2#")
				sneeded=$(echo ${needed} | tr , ' ')
				rneeded=""
				for lib in ${sneeded}; do
					found=0
					for path in ${opath//:/ }; do
						[ -e "${ED}/${path}/${lib}" ] && found=1 && break
					done
					[ "${found}" -eq 0 ] && rneeded="${rneeded},${lib}"
				done
				rneeded=${rneeded:1}
				if [ -n "${rneeded}" ]; then
					echo "${obj} ${rneeded}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED
					echo "${arch};${obj};${soname};${rpath};${rneeded}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED.PECOFF.1
				fi
			fi
		done }
		
		if [[ ${insecure_rpath} -eq 1 ]] ; then
			die "Aborting due to serious QA concerns with RUNPATH/RPATH"
		elif [[ -n ${die_msg} ]] && has stricter ${FEATURES} ; then
			die "Aborting due to QA concerns: ${die_msg}"
		fi

		local _so_ext='.so*'

		case "${CHOST}" in
			*-winnt*) _so_ext=".dll" ;; # no "*" intentionally!
		esac

		# Run some sanity checks on shared libraries
		for d in "${ED}"lib* "${ED}"usr/lib* ; do
			[[ -d "${d}" ]] || continue
			f=$(find "${d}" -name "lib*${_so_ext}" -print0 | \
				xargs -0 ${_pfx_scan} | while IFS=";" read arch obj soname rpath needed; \
				do [[ -z "${soname}" ]] && echo "${obj}"; done)
			if [[ -n ${f} ]] ; then
				vecho -ne '\a\n'
				eqawarn "QA Notice: The following shared libraries lack a SONAME"
				eqawarn "${f}"
				vecho -ne '\a\n'
				sleep 1
			fi

			f=$(find "${d}" -name "lib*${_so_ext}" -print0 | \
				xargs -0 ${_pfx_scan} | while IFS=";" read arch obj soname rpath needed; \
				do [[ -z "${needed}" ]] && echo "${obj}"; done)
			if [[ -n ${f} ]] ; then
				vecho -ne '\a\n'
				eqawarn "QA Notice: The following shared libraries lack NEEDED entries"
				eqawarn "${f}"
				vecho -ne '\a\n'
				sleep 1
			fi
		done

		PORTAGE_QUIET=${tmp_quiet}
	fi
}

install_qa_check_xcoff() {
	if ! has binchecks ${RESTRICT}; then
		local tmp_quiet=${PORTAGE_QUIET}
		local queryline deplib
		local insecure_rpath_list= undefined_symbols_list=

		# display warnings when using stricter because we die afterwards
		if has stricter ${FEATURES} ; then
			unset PORTAGE_QUIET
		fi

		rm -f "${PORTAGE_BUILDDIR}"/build-info/NEEDED.XCOFF.1

		local neededfd
		for neededfd in {3..1024} none; do ( : <&${neededfd} ) 2>/dev/null || break; done
		[[ ${neededfd} != none ]] || die "cannot find free file descriptor handle"

		eval "exec ${neededfd}>\"${PORTAGE_BUILDDIR}\"/build-info/NEEDED.XCOFF.1" || die "cannot open ${PORTAGE_BUILDDIR}/build-info/NEEDED.XCOFF.1"

		(	# work around a problem in /usr/bin/dump (used by aixdll-query)
			# dumping core when path names get too long.
			cd "${ED}" >/dev/null &&
			find . -not -type d -exec \
				aixdll-query '{}' FILE MEMBER FLAGS FORMAT RUNPATH DEPLIBS ';'
		) > "${T}"/needed 2>/dev/null

		# Symlinking shared archive libraries is not a good idea on aix,
		# as there is nothing like "soname" on pure filesystem level.
		# So we create a copy instead of the symlink.
		local prev_FILE=
		local FILE MEMBER FLAGS FORMAT RUNPATH DEPLIBS
		while read queryline
		do
			FILE= MEMBER= FLAGS= FORMAT= RUNPATH= DEPLIBS=
			eval ${queryline}
			FILE=${FILE#./}

			if [[ ${prev_FILE} != ${FILE} ]]; then
				if [[ " ${FLAGS} " == *" SHROBJ "* && -h ${ED}${FILE} ]]; then
					prev_FILE=${FILE}
					local target=$(readlink "${ED}${FILE}")
					if [[ ${target} == /* ]]; then
						target=${D}${target}
					else
						target=${FILE%/*}/${target}
					fi
					rm -f "${ED}${FILE}" || die "cannot prune ${FILE}"
					cp -f "${ED}${target}" "${ED}${FILE}" || die "cannot copy ${target} to ${FILE}"
				fi
			fi
		done <"${T}"/needed

		prev_FILE=
		while read queryline
		do
			FILE= MEMBER= FLAGS= FORMAT= RUNPATH= DEPLIBS=
			eval ${queryline}
			FILE=${FILE#./}

			if [[ -n ${MEMBER} && ${prev_FILE} != ${FILE} ]]; then
				# Save NEEDED information for each archive library stub
				# even if it is static only: the already installed archive
				# may contain shared objects to be preserved.
				echo "${FORMAT##* }${FORMAT%%-*};${EPREFIX}/${FILE};${FILE##*/};;" >&${neededfd}
			fi
			prev_FILE=${FILE}

			# shared objects have both EXEC and SHROBJ flags,
			# while executables have EXEC flag only.
			[[ " ${FLAGS} " == *" EXEC "* ]] || continue

			# Make sure we disallow insecure RUNPATH's
			# Don't want paths that point to the tree where the package was built
			# (older, broken libtools would do this).  Also check for null paths
			# because the loader will search $PWD when it finds null paths.
			# And we really want absolute paths only.
			if [[ -n $(echo ":${RUNPATH}:" | grep -E "(${PORTAGE_BUILDDIR}|::|:[^/])") ]]; then
				insecure_rpath_list="${insecure_rpath_list}\n${FILE}${MEMBER:+[${MEMBER}]}"
			fi

			local needed=
			[[ -n ${MEMBER} ]] && needed=${FILE##*/}
			for deplib in ${DEPLIBS}; do
				eval deplib=${deplib}
				if [[ ${deplib} == '.' || ${deplib} == '..' ]]; then
					# Although we do have runtime linking, we don't want undefined symbols.
					# AIX does indicate this by needing either '.' or '..'
					undefined_symbols_list="${undefined_symbols_list}\n${FILE}"
				else
					needed="${needed}${needed:+,}${deplib}"
				fi
			done

			FILE=${EPREFIX}/${FILE}

			[[ -n ${MEMBER} ]] && MEMBER="[${MEMBER}]"
			# Save NEEDED information
			echo "${FORMAT##* }${FORMAT%%-*};${FILE}${MEMBER};${FILE##*/}${MEMBER};${RUNPATH};${needed}" >&${neededfd}
		done <"${T}"/needed

		eval "exec ${neededfd}>&-" || die "cannot close handle to ${PORTAGE_BUILDDIR}/build-info/NEEDED.XCOFF.1"

		if [[ -n ${undefined_symbols_list} ]]; then
			vecho -ne '\a\n'
			eqawarn "QA Notice: The following files contain undefined symbols."
			eqawarn " Please file a bug about this at http://bugs.gentoo.org/"
			eqawarn " with 'prefix' as the maintaining herd of the package."
			eqawarn "${undefined_symbols_list}"
			vecho -ne '\a\n'
		fi

		if [[ -n ${insecure_rpath_list} ]] ; then
			vecho -ne '\a\n'
			eqawarn "QA Notice: The following files contain insecure RUNPATH's"
			eqawarn " Please file a bug about this at http://bugs.gentoo.org/"
			eqawarn " with 'prefix' as the maintaining herd of the package."
			eqawarn "${insecure_rpath_list}"
			vecho -ne '\a\n'
			if has stricter ${FEATURES} ; then
				insecure_rpath=1
			fi
		fi

		if [[ ${insecure_rpath} -eq 1 ]] ; then
			die "Aborting due to serious QA concerns with RUNPATH/RPATH"
		elif [[ -n ${die_msg} ]] && has stricter ${FEATURES} ; then
			die "Aborting due to QA concerns: ${die_msg}"
		fi

		PORTAGE_QUIET=${tmp_quiet}
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
		quiet_mode || einfo "Removing ${no_inst}"
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

preinst_aix() {
	if [[ ${CHOST} != *-aix* ]] || has binchecks ${RESTRICT}; then
		return 0
	fi
	local ar strip
	if type ${CHOST}-ar >/dev/null 2>&1 && type ${CHOST}-strip >/dev/null 2>&1; then
		ar=${CHOST}-ar
		strip=${CHOST}-strip
	elif [[ ${CBUILD} == "${CHOST}" ]] && type ar >/dev/null 2>&1 && type strip >/dev/null 2>&1; then
		ar=ar
		strip=strip
	elif [[ -x /usr/ccs/bin/ar && -x /usr/ccs/bin/strip ]]; then
		ar=/usr/ccs/bin/ar
		strip=/usr/ccs/bin/strip
	else
		die "cannot find where to use 'ar' and 'strip' from"
	fi
	local archives_members= archives=() helperfiles=()
	local archive_member soname runpath needed archive contentmember
	while read archive_member; do
		archive_member=${archive_member#*;${EPREFIX}/} # drop "^type;EPREFIX/"
		soname=${archive_member#*;}
		runpath=${soname#*;}
		needed=${runpath#*;}
		soname=${soname%%;*}
		runpath=${runpath%%;*}
		archive_member=${archive_member%%;*} # drop ";soname;runpath;needed$"
		archive=${archive_member%[*}
		if [[ ${archive_member} != *'['*']' ]]; then
			if [[ "${soname};${runpath};${needed}" == "${archive##*/};;" && -e ${EROOT}${archive} ]]; then
				# most likely is an archive stub that already exists,
				# may have to preserve members being a shared object.
				archives[${#archives[@]}]=${archive}
			fi
			continue
		fi
		archives_members="${archives_members}:(${archive_member}):"
		contentmember="${archive%/*}/.${archive##*/}${archive_member#${archive}}"
		# portage does os.lstat() on merged files every now
		# and then, so keep stamp-files for archive members
		# around to get the preserve-libs feature working.
		helperfiles[${#helperfiles[@]}]=${ED}${contentmember}
	done < "${PORTAGE_BUILDDIR}"/build-info/NEEDED.XCOFF.1
	if [[ ${#helperfiles[@]} > 0 ]]; then
		rm -f "${helperfiles[@]}" || die "cannot prune ${helperfiles[@]}"
		local f prev=
		for f in "${helperfiles[@]}"
		do
			if [[ -z ${prev} ]]; then
				{	echo "Please leave this file alone, it is an important helper"
					echo "for portage to implement the 'preserve-libs' feature on AIX." 
				} > "${f}" || die "cannot create ${f}"
				chmod 0400 "${f}" || die "cannot chmod ${f}"
				prev=${f}
			else
				ln "${prev}" "${f}" || die "cannot create hardlink ${f}"
			fi
		done
	fi

	local preservemembers libmetadir prunedirs=()
	local FILE MEMBER FLAGS
	for archive in "${archives[@]}"; do
		preservemembers=
		while read line; do
			[[ -n ${line} ]] || continue
			FILE= MEMBER= FLAGS=
			eval ${line}
			[[ ${FILE} == ${EROOT}${archive} ]] ||
			die "invalid result of aixdll-query for ${EROOT}${archive}"
			[[ -n ${MEMBER} && " ${FLAGS} " == *" SHROBJ "* ]] || continue
			[[ ${archives_members} == *":(${archive}[${MEMBER}]):"* ]] && continue
			preservemembers="${preservemembers} ${MEMBER}"
		done <<-EOF
			$(aixdll-query "${EROOT}${archive}" FILE MEMBER FLAGS)
		EOF
		[[ -n ${preservemembers} ]] || continue
		einfo "preserving (on spec) ${archive}[${preservemembers# }]"
		libmetadir=${ED}${archive%/*}/.${archive##*/}
		mkdir "${libmetadir}" || die "cannot create ${libmetadir}"
		pushd "${libmetadir}" >/dev/null || die "cannot cd to ${libmetadir}"
		${ar} -X32_64 -x "${EROOT}${archive}" ${preservemembers} || die "cannot unpack ${EROOT}${archive}"
		chmod u+w ${preservemembers} || die "cannot chmod${preservemembers}"
		${strip} -X32_64 -e ${preservemembers} || die "cannot strip${preservemembers}"
		${ar} -X32_64 -q "${ED}${archive}" ${preservemembers} || die "cannot update ${archive}"
		eend $?
		popd >/dev/null || die "cannot leave ${libmetadir}"
		prunedirs[${#prunedirs[@]}]=${libmetadir}
	done
	[[ ${#prunedirs[@]} == 0 ]] ||
	rm -rf "${prunedirs[@]}" || die "cannot prune ${prunedirs[@]}"
	return 0
}

postinst_aix() {
	if [[ ${CHOST} != *-aix* ]] || has binchecks ${RESTRICT}; then
		return 0
	fi
	local MY_PR=${PR%r0}
	local ar strip
	if type ${CHOST}-ar >/dev/null 2>&1 && type ${CHOST}-strip >/dev/null 2>&1; then
		ar=${CHOST}-ar
		strip=${CHOST}-strip
	elif [[ ${CBUILD} == "${CHOST}" ]] && type ar >/dev/null 2>&1 && type strip >/dev/null 2>&1; then
		ar=ar
		strip=strip
	elif [[ -x /usr/ccs/bin/ar && -x /usr/ccs/bin/strip ]]; then
		ar=/usr/ccs/bin/ar
		strip=/usr/ccs/bin/strip
	else
		die "cannot find where to use 'ar' and 'strip' from"
	fi
	local archives_members= archives=() activearchives=
	local archive_member soname runpath needed
	while read archive_member; do
		archive_member=${archive_member#*;${EPREFIX}/} # drop "^type;EPREFIX/"
		soname=${archive_member#*;}
		runpath=${soname#*;}
		needed=${runpath#*;}
		soname=${soname%%;*}
		runpath=${runpath%%;*}
		archive_member=${archive_member%%;*} # drop ";soname;runpath;needed$"
		[[ ${archive_member} == *'['*']' ]] && continue
		[[ "${soname};${runpath};${needed}" == "${archive_member##*/};;" ]] || continue
		# most likely is an archive stub, we might have to
		# drop members being preserved shared objects.
		archives[${#archives[@]}]=${archive_member}
		activearchives="${activearchives}:(${archive_member}):"
	done < "${PORTAGE_BUILDDIR}"/build-info/NEEDED.XCOFF.1

	local type allcontentmembers= oldarchives=()
	local contentmember
	while read type contentmember; do
		[[ ${type} == 'obj' ]] || continue
		contentmember=${contentmember% *} # drop " timestamp$"
		contentmember=${contentmember% *} # drop " hash$"
		[[ ${contentmember##*/} == *'['*']' ]] || continue
		contentmember=${contentmember#${EPREFIX}/}
		allcontentmembers="${allcontentmembers}:(${contentmember}):"
		contentmember=${contentmember%[*}
		contentmember=${contentmember%/.*}/${contentmember##*/.}
		[[ ${activearchives} == *":(${contentmember}):"* ]] && continue
		oldarchives[${#oldarchives[@]}]=${contentmember}
	done < "${EPREFIX}/var/db/pkg/${CATEGORY}/${P}${MY_PR:+-}${MY_PR}/CONTENTS"

	local archive line delmembers
	local FILE MEMBER FLAGS
	for archive in "${archives[@]}"; do
		[[ -r ${EROOT}${archive} && -w ${EROOT}${archive} ]] ||
		chmod a+r,u+w "${EROOT}${archive}" || die "cannot chmod ${EROOT}${archive}"
		delmembers=
		while read line; do
			[[ -n ${line} ]] || continue
			FILE= MEMBER= FLAGS=
			eval ${line}
			[[ ${FILE} == "${EROOT}${archive}" ]] ||
			die "invalid result '${FILE}' of aixdll-query, expected '${EROOT}${archive}'"
			[[ -n ${MEMBER} && " ${FLAGS} " == *" SHROBJ "* ]] || continue
			[[ ${allcontentmembers} == *":(${archive%/*}/.${archive##*/}[${MEMBER}]):"* ]] && continue
			delmembers="${delmembers} ${MEMBER}"
		done <<-EOF
			$(aixdll-query "${EROOT}${archive}" FILE MEMBER FLAGS)
		EOF
		[[ -n ${delmembers} ]] || continue
		einfo "dropping ${archive}[${delmembers# }]"
		rm -f "${EROOT}${archive}".new || die "cannot prune ${EROOT}${archive}.new"
		cp "${EROOT}${archive}" "${EROOT}${archive}".new || die "cannot backup ${archive}"
		${ar} -X32_64 -z -o -d "${EROOT}${archive}".new ${delmembers} || die "cannot remove${delmembers} from ${archive}.new"
		mv -f "${EROOT}${archive}".new "${EROOT}${archive}" || die "cannot put ${EROOT}${archive} in place"
		eend $?
	done
	local libmetadir keepmembers prunedirs=()
	for archive in "${oldarchives[@]}"; do
		[[ -r ${EROOT}${archive} && -w ${EROOT}${archive} ]] ||
		chmod a+r,u+w "${EROOT}${archive}" || die "cannot chmod ${EROOT}${archive}"
		keepmembers=
		while read line; do
			FILE= MEMBER= FLAGS=
			eval ${line}
			[[ ${FILE} == "${EROOT}${archive}" ]] ||
			die "invalid result of aixdll-query for ${EROOT}${archive}"
			[[ -n ${MEMBER} && " ${FLAGS} " == *" SHROBJ "* ]] || continue
			[[ ${allcontentmembers} == *":(${archive%/*}/.${archive##*/}[${MEMBER}]):"* ]] || continue
			keepmembers="${keepmembers} ${MEMBER}"
		done <<-EOF
			$(aixdll-query "${EROOT}${archive}" FILE MEMBER FLAGS)
		EOF

		if [[ -n ${keepmembers} ]]; then
			einfo "preserving (extra)${keepmembers}"
			libmetadir=${EROOT}${archive%/*}/.${archive##*/}
			[[ ! -e ${libmetadir} ]] || rm -rf "${libmetadir}" || die "cannot prune ${libmetadir}"
			mkdir "${libmetadir}" || die "cannot create ${libmetadir}"
			pushd "${libmetadir}" >/dev/null || die "cannot cd to ${libmetadir}"
			${ar} -X32_64 -x "${EROOT}${archive}" ${keepmembers} || die "cannot unpack ${archive}"
			${strip} -X32_64 -e ${keepmembers} || die "cannot strip ${keepmembers}"
			rm -f "${EROOT}${archive}.new" || die "cannot prune ${EROOT}${archive}.new"
			${ar} -X32_64 -q "${EROOT}${archive}.new" ${keepmembers} || die "cannot create ${EROOT}${archive}.new"
			mv -f "${EROOT}${archive}.new" "${EROOT}${archive}" || die "cannot put ${EROOT}${archive} in place"
			popd > /dev/null || die "cannot leave ${libmetadir}"
			prunedirs[${#prunedirs[@]}]=${libmetadir}
			eend $?
		fi
	done
	[[ ${#prunedirs[@]} == 0 ]] ||
	rm -rf "${prunedirs[@]}" || die "cannot prune ${prunedirs[@]}"
	return 0
}

preinst_mask() {
	if [ -z "${D}" ]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi

	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local ED=${D} ;; esac

	# Make sure $PWD is not ${D} so that we don't leave gmon.out files
	# in there in case any tools were built with -pg in CFLAGS.
	cd "${T}"

	# remove man pages, info pages, docs if requested
	local f
	for f in man info doc; do
		if has no${f} $FEATURES; then
			INSTALL_MASK="${INSTALL_MASK} ${EPREFIX}/usr/share/${f}"
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

	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local ED=${D} ;; esac

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

	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local ED=${D} ;; esac

	# total suid control.
	if has suidctl $FEATURES; then
		local i sfconf x
		sfconf=${PORTAGE_CONFIGROOT}etc/portage/suidctl.conf
		# sandbox prevents us from writing directly
		# to files outside of the sandbox, but this
		# can easly be bypassed using the addwrite() function
		addwrite "${sfconf}"
		vecho ">>> Performing suid scan in ${ED}"
		for i in $(find "${ED}" -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [ -s "${sfconf}" ]; then
				install_path=/${i#${ED}}
				if grep -q "^${install_path}\$" "${sfconf}" ; then
					vecho "- ${install_path} is an approved suid file"
				else
					vecho ">>> Removing sbit on non registered ${install_path}"
					for x in 5 4 3 2 1 0; do sleep 0.25 ; done
					ls_ret=$(ls -ldh "${i}")
					chmod ugo-s "${i}"
					grep "^#${install_path}$" "${sfconf}" > /dev/null || {
						vecho ">>> Appending commented out entry to ${sfconf} for ${PF}"
						echo "## ${ls_ret%${ED}*}${install_path}" >> "${sfconf}"
						echo "#${install_path}" >> "${sfconf}"
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
	if [ -z "${D}" ]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi
	if has selinux ${FEATURES}; then
		# SELinux file labeling (needs to always be last in dyn_preinst)
		# only attempt to label if setfiles is executable
		# and 'context' is available on selinuxfs.
		if [ -f "${EPREFIX}"/selinux/context -a -x "${EPREFIX}"/usr/sbin/setfiles -a -x "${EPREFIX}"/usr/sbin/selinuxconfig ]; then
			vecho ">>> Setting SELinux security labels"
			(
				eval "$("${EPREFIX}"/usr/sbin/selinuxconfig)" || \
					die "Failed to determine SELinux policy paths.";
	
				addwrite /selinux/context;
	
				"${EPREFIX}"/usr/sbin/setfiles "${file_contexts_path}" -r "${D}" "${D}"
			) || die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			vecho "!!! Unable to set SELinux security labels"
		fi
	fi
}

dyn_package() {

	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local ED=${D} ;; esac

	# Make sure $PWD is not ${D} so that we don't leave gmon.out files
	# in there in case any tools were built with -pg in CFLAGS.
	cd "${T}"
	install_mask "${ED}" "${PKG_INSTALL_MASK}"
	local tar_options=""
	[[ $PORTAGE_VERBOSE = 1 ]] && tar_options+=" -v"
	# Sandbox is disabled in case the user wants to use a symlink
	# for $PKGDIR and/or $PKGDIR/All.
	export SANDBOX_ON="0"
	[ -z "${PORTAGE_BINPKG_TMPFILE}" ] && \
		die "PORTAGE_BINPKG_TMPFILE is unset"
	mkdir -p "${PORTAGE_BINPKG_TMPFILE%/*}" || die "mkdir failed"
	tar $tar_options -cf - $PORTAGE_BINPKG_TAR_OPTS -C "${D}" . | \
		$PORTAGE_BZIP2_COMMAND -c > "$PORTAGE_BINPKG_TMPFILE"
	assert "failed to pack binary package: '$PORTAGE_BINPKG_TMPFILE'"
	PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
		"${PORTAGE_PYTHON:-@PREFIX_PORTAGE_PYTHON@}" "$PORTAGE_BIN_PATH"/xpak-helper.py recompose \
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
	vecho ">>> Done."
	cd "${PORTAGE_BUILDDIR}"
	>> "$PORTAGE_BUILDDIR/.packaged" || \
		die "Failed to create $PORTAGE_BUILDDIR/.packaged"
}

dyn_spec() {
	local sources_dir=/usr/src/rpm/SOURCES
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

	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local EPREFIX= ;; esac

	cd "${T}" || die "cd failed"
	local machine_name=$(uname -m)
	local dest_dir=${EPREFIX}/usr/src/rpm/RPMS/${machine_name}
	addwrite ${EPREFIX}/usr/src/rpm
	addwrite "${RPMDIR}"
	dyn_spec
	rpmbuild -bb --clean --rmsource "${PF}.spec" || die "Failed to integrate rpm spec file"
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
	source_all_bashrcs
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
