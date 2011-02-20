#!/bin/bash
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

source "${PORTAGE_BIN_PATH:-/usr/lib/portage/bin}/ebuild.sh"

install_symlink_html_docs() {
	cd "${D}" || die "cd failed"
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

	# Canonicalize path names and check for their existence.
	real_d=$(canonicalize "${D}")
	for (( i = 0; i < ${#PORTAGE_DOCOMPRESS[@]}; i++ )); do
		real_f=$(canonicalize "${D}${PORTAGE_DOCOMPRESS[i]}")
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
		real_f=$(canonicalize "${D}${PORTAGE_DOCOMPRESS_SKIP[i]}")
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
		if [[ -d ${D}${f} ]]; then
			incl_d[${#incl_d[@]}]=${f}
		else
			incl_f[${#incl_f[@]}]=${f}
		fi
	done

	# Queue up for compression.
	# ecompress{,dir} doesn't like to be called with empty argument lists.
	[[ ${#incl_d[@]} -gt 0 ]] && ecompressdir --queue "${incl_d[@]}"
	[[ ${#incl_f[@]} -gt 0 ]] && ecompress --queue "${incl_f[@]/#/${D}}"
	[[ ${#exclude[@]} -gt 0 ]] && ecompressdir --ignore "${exclude[@]}"
	return 0
}

install_qa_check() {
	local f x

	cd "${D}" || die "cd failed"

	export STRIP_MASK
	prepall
	hasq "${EAPI}" 0 1 2 3 || prepcompress
	ecompressdir --dequeue
	ecompress --dequeue

	f=
	for x in etc/app-defaults usr/man usr/info usr/X11R6 usr/doc usr/locale ; do
		[[ -d $D/$x ]] && f+="  $x\n"
	done

	if [[ -n $f ]] ; then
		eqawarn "QA Notice: This ebuild installs into the following deprecated directories:"
		eqawarn
		eqawarn "$f"
	fi

	# Now we look for all world writable files.
	local i
	for i in $(find "${D}/" -type f -perm -2); do
		vecho "QA Security Notice:"
		vecho "- ${i:${#D}:${#i}} will be a world writable file."
		vecho "- This may or may not be a security problem, most of the time it is one."
		vecho "- Please double check that $PF really needs a world writeable bit and file bugs accordingly."
		sleep 1
	done

	if type -P scanelf > /dev/null && ! hasq binchecks ${RESTRICT}; then
		local qa_var insecure_rpath=0 tmp_quiet=${PORTAGE_QUIET}
		local x

		# display warnings when using stricter because we die afterwards
		if has stricter ${FEATURES} ; then
			unset PORTAGE_QUIET
		fi

		# Make sure we disallow insecure RUNPATH/RPATHs
		# Don't want paths that point to the tree where the package was built
		# (older, broken libtools would do this).  Also check for null paths
		# because the loader will search $PWD when it finds null paths.
		f=$(scanelf -qyRF '%r %p' "${D}" | grep -E "(${PORTAGE_BUILDDIR}|: |::|^:|^ )")
		# Reject set*id binaries with $ORIGIN in RPATH #260331
		x=$(
			find "${D}" -type f \( -perm -u+s -o -perm -g+s \) -print0 | \
			xargs -0 scanelf -qyRF '%r %p' | grep '$ORIGIN'
		)
		if [[ -n ${f}${x} ]] ; then
			vecho -ne '\n'
			eqawarn "QA Notice: The following files contain insecure RUNPATHs"
			eqawarn " Please file a bug about this at http://bugs.gentoo.org/"
			eqawarn " with the maintaining herd of the package."
			eqawarn "${f}${f:+${x:+\n}}${x}"
			vecho -ne '\n'
			if [[ -n ${x} ]] || has stricter ${FEATURES} ; then
				insecure_rpath=1
			else
				vecho "Auto fixing rpaths for ${f}"
				TMPDIR=${PORTAGE_BUILDDIR} scanelf -BXr ${f} -o /dev/null
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
		f=$(scanelf -qyRF '%t %p' "${D}" | grep -v 'usr/lib/debug/')
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
					f=$(scanelf -qyRAF '%e %p' "${D}" | grep -v 'usr/lib/debug/')
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

		# Check for files built without respecting LDFLAGS
		if [[ "${LDFLAGS}" == *,--hash-style=gnu* ]] && [[ "${PN}" != *-bin ]] ; then
			qa_var="QA_DT_HASH_${ARCH/-/_}"
			eval "[[ -n \${!qa_var} ]] && QA_DT_HASH=(\"\${${qa_var}[@]}\")"
			f=$(scanelf -qyRF '%k %p' -k .hash "${D}" | sed -e "s:\.hash ::")
			if [[ -n ${f} ]] ; then
				echo "${f}" > "${T}"/scanelf-ignored-LDFLAGS.log
				if [ "${QA_STRICT_DT_HASH-unset}" == unset ] ; then
					if [[ ${#QA_DT_HASH[@]} -gt 1 ]] ; then
						for x in "${QA_DT_HASH[@]}" ; do
							sed -e "s#^${x#/}\$##" -i "${T}"/scanelf-ignored-LDFLAGS.log
						done
					else
						local shopts=$-
						set -o noglob
						for x in ${QA_DT_HASH} ; do
							sed -e "s#^${x#/}\$##" -i "${T}"/scanelf-ignored-LDFLAGS.log
						done
						set +o noglob
						set -${shopts}
					fi
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

		if [[ ${insecure_rpath} -eq 1 ]] ; then
			die "Aborting due to serious QA concerns with RUNPATH/RPATH"
		elif [[ -n ${die_msg} ]] && has stricter ${FEATURES} ; then
			die "Aborting due to QA concerns: ${die_msg}"
		fi

		# Check for shared libraries lacking SONAMEs
		qa_var="QA_SONAME_${ARCH/-/_}"
		eval "[[ -n \${!qa_var} ]] && QA_SONAME=(\"\${${qa_var}[@]}\")"
		f=$(scanelf -ByF '%S %p' "${D}"{,usr/}lib*/lib*.so* | gawk '$2 == "" { print }' | sed -e "s:^[[:space:]]${D}:/:")
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
		f=$(scanelf -ByF '%n %p' "${D}"{,usr/}lib*/lib*.so* | gawk '$2 == "" { print }' | sed -e "s:^[[:space:]]${D}:/:")
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

	local unsafe_files=$(find "${D}" -type f '(' -perm -2002 -o -perm -4002 ')')
	if [[ -n ${unsafe_files} ]] ; then
		eqawarn "QA Notice: Unsafe files detected (set*id and world writable)"
		eqawarn "${unsafe_files}"
		die "Unsafe files found in \${D}.  Portage will not install them."
	fi

	if [[ -d ${D}/${D} ]] ; then
		declare -i INSTALLTOD=0
		for i in $(find "${D}/${D}/"); do
			eqawarn "QA Notice: /${i##${D}/${D}} installed in \${D}/\${D}"
			((INSTALLTOD++))
		done
		die "Aborting due to QA concerns: ${INSTALLTOD} files installed in ${D}/${D}"
		unset INSTALLTOD
	fi

	# Sanity check syntax errors in init.d scripts
	local d
	for d in /etc/conf.d /etc/init.d ; do
		[[ -d ${D}/${d} ]] || continue
		for i in "${D}"/${d}/* ; do
			[[ -L ${i} ]] && continue
			# if empty conf.d/init.d dir exists (baselayout), then i will be "/etc/conf.d/*" and not exist
			[[ ! -e ${i} ]] && continue
			bash -n "${i}" || die "The init.d file has syntax errors: ${i}"
		done
	done

	# this should help to ensure that all (most?) shared libraries are executable
	# and that all libtool scripts / static libraries are not executable
	local j
	for i in "${D}"opt/*/lib{,32,64} \
	         "${D}"lib{,32,64}       \
	         "${D}"usr/lib{,32,64}   \
	         "${D}"usr/X11R6/lib{,32,64} ; do
		[[ ! -d ${i} ]] && continue

		for j in "${i}"/*.so.* "${i}"/*.so ; do
			[[ ! -e ${j} ]] && continue
			[[ -L ${j} ]] && continue
			[[ -x ${j} ]] && continue
			vecho "making executable: ${j#${D}}"
			chmod +x "${j}"
		done

		for j in "${i}"/*.a "${i}"/*.la ; do
			[[ ! -e ${j} ]] && continue
			[[ -L ${j} ]] && continue
			[[ ! -x ${j} ]] && continue
			vecho "removing executable bit: ${j#${D}}"
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
	for a in "${D}"usr/lib*/*.a ; do
		s=${a%.a}.so
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
	f=$(ls "${D}"lib*/*.{a,la} 2>/dev/null)
	if [[ -n ${f} ]] ; then
		vecho -ne '\n'
		eqawarn "QA Notice: Excessive files found in the / partition"
		eqawarn "${f}"
		vecho -ne '\n'
		die "static archives (*.a) and libtool library files (*.la) do not belong in /"
	fi

	# Verify that the libtool files don't contain bogus $D entries.
	local abort=no gentoo_bug=no always_overflow=no
	for a in "${D}"usr/lib*/*.la ; do
		s=${a##*/}
		if grep -qs "${D}" "${a}" ; then
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
			": warning: dereferencing type-punned pointer will break strict-aliasing rules$"
			": warning: dereferencing pointer .* does break strict-aliasing rules$"
			": warning: implicit declaration of function "
			": warning: incompatible implicit declaration of built-in function "
			": warning: is used uninitialized in this function$" # we'll ignore "may" and "might"
			": warning: comparisons like X<=Y<=Z do not have their mathematical meaning$"
			": warning: null argument where non-null required "
			": warning: array subscript is below array bounds$"
			": warning: array subscript is above array bounds$"
			": warning: attempt to free a non-heap object"
			": warning: .* called with .*bigger.* than .* destination buffer$"
			": warning: call to .* will always overflow destination buffer$"
			": warning: assuming pointer wraparound does not occur when comparing "
			": warning: hex escape sequence out of range$"
			": warning: [^ ]*-hand operand of comma .*has no effect$"
			": warning: converting to non-pointer type .* from NULL"
			": warning: NULL used in arithmetic$"
			": warning: passing NULL to non-pointer argument"
			": warning: the address of [^ ]* will always evaluate as"
			": warning: the address of [^ ]* will never be NULL"
			": warning: too few arguments for format"
			": warning: reference to local variable .* returned"
			": warning: returning reference to temporary"
			": warning: function returns address of local variable"
			# this may be valid code :/
			#": warning: multi-character character constant$"
			# need to check these two ...
			#": warning: assuming signed overflow does not occur when "
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
				#	": warning: call to .* will always overflow destination buffer$") always_overflow=yes ;;
				#esac
				if [[ $always_overflow = yes ]] ; then
					eerror
					eerror "QA Notice: Package has poor programming practices which may compile"
					eerror "           fine but exhibit random runtime failures."
					eerror
					eerror "${f}"
					eerror
					eerror " Please file a bug about this at http://bugs.gentoo.org/"
					eerror " with the maintaining herd of the package."
					eerror
				else
					vecho -ne '\n'
					eqawarn "QA Notice: Package has poor programming practices which may compile"
					eqawarn "           fine but exhibit random runtime failures."
					eqawarn "${f}"
					vecho -ne '\n'
				fi
			fi
		done
		local cat_cmd=cat
		[[ $PORTAGE_LOG_FILE = *.gz ]] && cat_cmd=zcat
		[[ $reset_debug = 1 ]] && set -x
		f=$($cat_cmd "${PORTAGE_LOG_FILE}" | \
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
				eerror "QA Notice: Package has poor programming practices which may compile"
				eerror "           but will almost certainly crash on 64bit architectures."
				eerror
				eerror "${f}"
				eerror
				eerror " Please file a bug about this at http://bugs.gentoo.org/"
				eerror " with the maintaining herd of the package."
				eerror
			else
				vecho -ne '\n'
				eqawarn "QA Notice: Package has poor programming practices which may compile"
				eqawarn "           but will almost certainly crash on 64bit architectures."
				eqawarn "${f}"
				vecho -ne '\n'
			fi

		fi
		if [[ ${abort} == "yes" ]] ; then
			if [[ $gentoo_bug = yes || $always_overflow = yes ]] ; then
				die "install aborted due to" \
					"poor programming practices shown above"
			else
				echo "Please do not file a Gentoo bug and instead" \
				"report the above QA issues directly to the upstream" \
				"developers of this software." | fmt -w 70 | \
				while read -r line ; do eqawarn "${line}" ; done
				eqawarn "Homepage: ${HOMEPAGE}"
				hasq stricter ${FEATURES} && die "install aborted due to" \
					"poor programming practices shown above"
			fi
		fi
	fi

	# Portage regenerates this on the installed system.
	rm -f "${D}"/usr/share/info/dir{,.gz,.bz2}

	if hasq multilib-strict ${FEATURES} && \
	   [[ -x /usr/bin/file && -x /usr/bin/find ]] && \
	   [[ -n ${MULTILIB_STRICT_DIRS} && -n ${MULTILIB_STRICT_DENY} ]]
	then
		local abort=no dir file firstrun=yes
		MULTILIB_STRICT_EXEMPT=$(echo ${MULTILIB_STRICT_EXEMPT} | sed -e 's:\([(|)]\):\\\1:g')
		for dir in ${MULTILIB_STRICT_DIRS} ; do
			[[ -d ${D}/${dir} ]] || continue
			for file in $(find ${D}/${dir} -type f | grep -v "^${D}/${dir}/${MULTILIB_STRICT_EXEMPT}"); do
				if file ${file} | egrep -q "${MULTILIB_STRICT_DENY}" ; then
					if [[ ${firstrun} == yes ]] ; then
						echo "Files matching a file type that is not allowed:"
						firstrun=no
					fi
					abort=yes
					echo "   ${file#${D}//}"
				fi
			done
		done
		[[ ${abort} == yes ]] && die "multilib-strict check failed!"
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

preinst_bsdflags() {
	hasq chflags $FEATURES || return
	# Save all the file flags for restoration after installation.
	mtree -c -p "${D}" -k flags > "${T}/bsdflags.mtree"
	# Remove all the file flags so that the merge phase can do anything
	# necessary.
	chflags -R noschg,nouchg,nosappnd,nouappnd "${D}"
	chflags -R nosunlnk,nouunlnk "${D}" 2>/dev/null
}

postinst_bsdflags() {
	hasq chflags $FEATURES || return
	# Restore all the file flags that were saved before installation.
	mtree -e -p "${ROOT}" -U -k flags < "${T}/bsdflags.mtree" &> /dev/null
}

preinst_mask() {
	if [ -z "${D}" ]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi

	# Make sure $PWD is not ${D} so that we don't leave gmon.out files
	# in there in case any tools were built with -pg in CFLAGS.
	cd "${T}"

	# remove man pages, info pages, docs if requested
	local f
	for f in man info doc; do
		if hasq no${f} $FEATURES; then
			INSTALL_MASK="${INSTALL_MASK} /usr/share/${f}"
		fi
	done

	install_mask "${D}" "${INSTALL_MASK}"

	# remove share dir if unnessesary
	if hasq nodoc $FEATURES -o hasq noman $FEATURES -o hasq noinfo $FEATURES; then
		rmdir "${D}usr/share" &> /dev/null
	fi
}

preinst_sfperms() {
	if [ -z "${D}" ]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi
	# Smart FileSystem Permissions
	if hasq sfperms $FEATURES; then
		local i
		find "${D}" -type f -perm -4000 -print0 | \
		while read -r -d $'\0' i ; do
			if [ -n "$(find "$i" -perm -2000)" ] ; then
				ebegin ">>> SetUID and SetGID: [chmod o-r] /${i#${D}}"
				chmod o-r "$i"
				eend $?
			else
				ebegin ">>> SetUID: [chmod go-r] /${i#${D}}"
				chmod go-r "$i"
				eend $?
			fi
		done
		find "${D}" -type f -perm -2000 -print0 | \
		while read -r -d $'\0' i ; do
			if [ -n "$(find "$i" -perm -4000)" ] ; then
				# This case is already handled
				# by the SetUID check above.
				true
			else
				ebegin ">>> SetGID: [chmod o-r] /${i#${D}}"
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
	# total suid control.
	if hasq suidctl $FEATURES; then
		local i sfconf x
		sfconf=${PORTAGE_CONFIGROOT}etc/portage/suidctl.conf
		# sandbox prevents us from writing directly
		# to files outside of the sandbox, but this
		# can easly be bypassed using the addwrite() function
		addwrite "${sfconf}"
		vecho ">>> Performing suid scan in ${D}"
		for i in $(find "${D}" -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [ -s "${sfconf}" ]; then
				install_path=/${i#${D}}
				if grep -q "^${install_path}\$" "${sfconf}" ; then
					vecho "- ${install_path} is an approved suid file"
				else
					vecho ">>> Removing sbit on non registered ${install_path}"
					for x in 5 4 3 2 1 0; do sleep 0.25 ; done
					ls_ret=$(ls -ldh "${i}")
					chmod ugo-s "${i}"
					grep "^#${install_path}$" "${sfconf}" > /dev/null || {
						vecho ">>> Appending commented out entry to ${sfconf} for ${PF}"
						echo "## ${ls_ret%${D}*}${install_path}" >> "${sfconf}"
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
	
				/usr/sbin/setfiles "${file_contexts_path}" -r "${D}" "${D}"
			) || die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			vecho "!!! Unable to set SELinux security labels"
		fi
	fi
}

dyn_package() {
	# Make sure $PWD is not ${D} so that we don't leave gmon.out files
	# in there in case any tools were built with -pg in CFLAGS.
	cd "${T}"
	install_mask "${PORTAGE_BUILDDIR}/image" "${PKG_INSTALL_MASK}"
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
	cd "${T}" || die "cd failed"
	local machine_name=$(uname -m)
	local dest_dir=/usr/src/rpm/RPMS/${machine_name}
	addwrite /usr/src/rpm
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
