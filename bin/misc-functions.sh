#!/usr/bin/env bash
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
	else
		# PREFIX LOCAL: ED needs not to exist, whereas D does
		[[ ! -d ${ED} && -d ${D} ]] && dodir /
		# END PREFIX LOCAL
	fi
	cd "${ED}" || die "cd failed"
	# Symlink the html documentation (if DOC_SYMLINKS_DIR is set in make.conf)
	if [[ -n "${DOC_SYMLINKS_DIR}" ]]; then
		local mydocdir docdir
		for docdir in "${HTMLDOC_DIR:-does/not/exist}" "${PF}/html" "${PF}/HTML" "${P}/html" "${P}/HTML" ; do
			if [[ -d "usr/share/doc/${docdir}" ]]; then
				mydocdir="/usr/share/doc/${docdir}"
			fi
		done
		if [[ -n "${mydocdir}" ]]; then
			local mysympath
			if [[ -z "${SLOT}" || "${SLOT%/*}" = "0" ]]; then
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

	# PREFIX LOCAL: ED needs not to exist, whereas D does
	cd "${D}" || die "cd failed"
	# END PREFIX LOCAL

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

	if has chflags $FEATURES ; then
		# Restore all the file flags that were saved earlier on.
		mtree -U -e -p "${ED}" -k flags < "${T}/bsdflags.mtree" &> /dev/null
	fi

	# PREFIX LOCAL:
	# anything outside the prefix should be caught by the Prefix QA
	# check, so if there's nothing in ED, we skip searching for QA
	# checks there, the specific QA funcs can hence rely on ED existing
	if [[ -d ${ED} ]] ; then
		case ${CHOST} in
			*-darwin*)
				# Mach-O platforms (NeXT, Darwin, OSX/macOS)
				install_qa_check_macho
			;;
			*-interix*|*-winnt*)
				# PECOFF platforms (Windows/Interix)
				install_qa_check_pecoff
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
				rpath=${l%%;*}; l=${l#*;}; [[ "${rpath}" = "  -  " ]] && rpath=""
				needed=${l%%;*}; l=${l#*;}

				# Infer implicit soname from basename (bug 715162).
				if [[ -z ${soname} && $(file "${D%/}${obj}") == *"SB shared object"* ]]; then
					soname=${obj##*/}
				fi

				echo "${obj} ${needed}"	>> "${PORTAGE_BUILDDIR}"/build-info/NEEDED
				echo "${arch#EM_};${obj};${soname};${rpath};${needed}" >> "${PORTAGE_BUILDDIR}"/build-info/NEEDED.ELF.2
			done <<< ${scanelf_output}
		fi

		[[ -n "${QA_SONAME_NO_SYMLINK}" ]] && \
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
}

install_qa_check_misc() {
	# If binpkg-dostrip is enabled, apply stripping before creating
	# the binary package.
	# Note: disabling it won't help with packages calling prepstrip directly.
	# We do this after the scanelf bits so that we can reuse the data. bug #749624.
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

	# Portage regenerates this on the installed system.
	rm -f "${ED%/}"/usr/share/info/dir{,.gz,.bz2} || die "rm failed!"
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
			__vecho -ne '\a\n'
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
			__vecho -ne '\a\n'
			eqawarn "QA Notice: Found wrongly named dynamic libraries on Darwin:"
			eqawarn "    ${f// /\n    }"
		fi
		rm -f "${T}/mach-o.check"
	fi

	install_name_is_relative() {
		case $1 in
			"@executable_path/"*)  return 0  ;;
			"@loader_path"/*)      return 0  ;;
			"@rpath/"*)            return 0  ;;
			*)                     return 1  ;;
		esac
	}

	# While we generate the NEEDED files, check that we don't get kernel
	# traps at runtime because of broken install_names on Darwin.
	rm -f "${T}"/.install_name_check_failed
	scanmacho -qyRF '%a;%p;%S;%n' "${D}" | { while IFS= read l ; do
		arch=${l%%;*}; l=${l#*;}
		obj="/${l%%;*}"; l=${l#*;}
		install_name=${l%%;*}; l=${l#*;}
		needed=${l%%;*}; l=${l#*;}

		ignore=
		qa_var="QA_IGNORE_INSTALL_NAME_FILES_${ARCH/-/_}"
		eval "[[ -n \${!qa_var} ]] &&
			QA_IGNORE_INSTALL_NAME_FILES=(\"\${${qa_var}[@]}\")"

		if [[ ${#QA_IGNORE_INSTALL_NAME_FILES[@]} -gt 1 ]] ; then
			for x in "${QA_IGNORE_INSTALL_NAME_FILES[@]}" ; do
				[[ ${obj##*/} == ${x} ]] && \
					ignore=true
			done
		else
			local shopts=$-
			set -o noglob
			for x in ${QA_IGNORE_INSTALL_NAME_FILES} ; do
				[[ ${obj##*/} == ${x} ]] && \
					ignore=true
			done
			set +o noglob
			set -${shopts}
		fi

		# See if the self-reference install_name points to an existing
		# and to be installed file.  This usually is a symlink for the
		# major version.
		if install_name_is_relative ${install_name} ; then
			# try to locate the library in the installed image
			local inpath=${install_name#@*/}
			local libl
			for libl in $(find "${ED}" -name "${inpath##*/}") ; do
				if [[ ${libl} == */${inpath} ]] ; then
					install_name=/${libl#${D}}
					break
				fi
			done
		fi
		if [[ ! -e ${D}${install_name} ]] ; then
			eqawarn "QA Notice: invalid self-reference install_name ${install_name} in ${obj}"
			# remember we are in an implicit subshell, that's
			# why we touch a file here ... ideally we should be
			# able to die correctly/nicely here
			[[ -z ${ignore} ]] && touch "${T}"/.install_name_check_failed
		fi

		# this is ugly, paths with spaces won't work
		for lib in ${needed//,/ } ; do
			if [[ ${lib} == ${D}* ]] ; then
				eqawarn "QA Notice: install_name references \${D}: ${lib} in ${obj}"
				[[ -z ${ignore} ]] && touch "${T}"/.install_name_check_failed
			elif [[ ${lib} == ${S}* ]] ; then
				eqawarn "QA Notice: install_name references \${S}: ${lib} in ${obj}"
				[[ -z ${ignore} ]] && touch "${T}"/.install_name_check_failed
			elif ! install_name_is_relative ${lib} ; then
				local isok=no
				if [[ -e ${lib} || -e ${D}${lib} ]] ; then
					isok=yes  # yay, we're ok
				elif [[ -e "${EROOT}"/MacOSX.sdk ]] ; then
					# trigger SDK mode, at least since Big Sur (11.0)
					# there are no libraries in /usr/lib any more, but
					# there are references too it (some library cache is
					# in place), yet we can validate it sort of is sane
					# by looking at the SDK metacaches, TAPI-files, .tbd
					# text versions of libraries, so just look there
					local tbd=${lib%.*}.tbd
					if [[ -e ${EROOT}/MacOSX.sdk/${lib%.*}.tbd ]] ; then
						isok=yes  # it's in the SDK, so ok
					elif [[ -e ${EROOT}/MacOSX.sdk/${lib}.tbd ]] ; then
						isok=yes  # this happens in case of Framework refs
					fi
				fi
				if [[ ${isok} == no ]] ; then
					eqawarn "QA Notice: invalid reference to ${lib} in ${obj}"
					[[ -z ${ignore} ]] && \
						touch "${T}"/.install_name_check_failed
				fi
			fi
		done

		# backwards compatibility
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
			__vecho -ne '\a\n'
			eqawarn "QA Notice: The following files contain insecure RUNPATH's"
			eqawarn " Please file a bug about this at http://bugs.gentoo.org/"
			eqawarn " with the maintaining herd of the package."
			eqawarn "${f}${f:+${x:+\n}}${x}"
			__vecho -ne '\a\n'
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
				__vecho -ne '\a\n'
				eqawarn "QA Notice: The following shared libraries lack a SONAME"
				eqawarn "${f}"
				__vecho -ne '\a\n'
				sleep 1
			fi

			f=$(find "${d}" -name "lib*${_so_ext}" -print0 | \
				xargs -0 ${_pfx_scan} | while IFS=";" read arch obj soname rpath needed; \
				do [[ -z "${needed}" ]] && echo "${obj}"; done)
			if [[ -n ${f} ]] ; then
				__vecho -ne '\a\n'
				eqawarn "QA Notice: The following shared libraries lack NEEDED entries"
				eqawarn "${f}"
				__vecho -ne '\a\n'
				sleep 1
			fi
		done

		PORTAGE_QUIET=${tmp_quiet}
	fi
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
	# Remove man pages, info pages, docs if requested. This is
	# implemented in bash in order to respect INSTALL_MASK settings
	# from bashrc.
	local f x
	for f in man info doc; do
		if has no${f} ${FEATURES}; then
		    # PREFIX LOCAL: use EPREFIX with path
			INSTALL_MASK="${INSTALL_MASK} ${EPREFIX}/usr/share/${f}"
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
	if [[ -z "${D}" ]]; then
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
			if [[ -n "$(find "$i" -perm -2000)" ]]; then
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
			if [[ -n "$(find "$i" -perm -4000)" ]]; then
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
	if [[ -z "${D}" ]]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi

	if ! ___eapi_has_prefix_variables; then
		local ED=${D}
	fi

	# Total suid control
	if has suidctl $FEATURES; then
		local i sfconf x
		sfconf=${PORTAGE_CONFIGROOT}etc/portage/suidctl.conf
		# sandbox prevents us from writing directly
		# to files outside of the sandbox, but this
		# can easly be bypassed using the addwrite() function
		addwrite "${sfconf}"
		__vecho ">>> Performing suid scan in ${ED}"
		for i in $(find "${ED}" -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [[ -s "${sfconf}" ]]; then
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
	if [[ -z "${D}" ]]; then
		 eerror "${FUNCNAME}: D is unset"
		 return 1
	fi
	if has selinux ${FEATURES}; then
		# SELinux file labeling (needs to execute after preinst)
		# only attempt to label if setfiles is executable
		# and 'context' is available on selinuxfs.
		if [[ -f /sys/fs/selinux/context && -x /usr/sbin/setfiles && -x /usr/sbin/selinuxconfig ]]; then
			__vecho ">>> Setting SELinux security labels"
			(
				eval "$(/usr/sbin/selinuxconfig)" || \
					die "Failed to determine SELinux policy paths.";

				addwrite /sys/fs/selinux/context

				/usr/sbin/setfiles -F -r "${D}" "${file_contexts_path}" "${D}"
			) || die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SELinux kernel
			# (like during a recovery situation)
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

	# Sandbox is disabled in case the user wants to use a symlink
	# for $PKGDIR and/or $PKGDIR/All.
	export SANDBOX_ON="0"
	[[ -z "${PORTAGE_BINPKG_TMPFILE}" ]] && \
		die "PORTAGE_BINPKG_TMPFILE is unset"
	mkdir -p "${PORTAGE_BINPKG_TMPFILE%/*}" || die "mkdir failed"

	if [[ "${BINPKG_FORMAT}" == "xpak" ]]; then
		local tar_options=""
		[[ $PORTAGE_VERBOSE = 1 ]] && tar_options+=" -v"
		has xattr ${FEATURES} && [[ $(tar --help 2> /dev/null) == *--xattrs* ]] && tar_options+=" --xattrs"
		[[ -z "${PORTAGE_COMPRESSION_COMMAND}" ]] && \
			die "PORTAGE_COMPRESSION_COMMAND is unset"
		tar $tar_options -cf - $PORTAGE_BINPKG_TAR_OPTS -C "${D}" . | \
			$PORTAGE_COMPRESSION_COMMAND > "$PORTAGE_BINPKG_TMPFILE"
		assert "failed to pack binary package: '$PORTAGE_BINPKG_TMPFILE'"
		# BEGIN PREFIX LOCAL: use PREFIX_PORTAGE_PYTHON fallback
		PYTHONPATH=${PORTAGE_PYTHONPATH:-${PORTAGE_PYM_PATH}} \
			"${PORTAGE_PYTHON:-@PREFIX_PORTAGE_PYTHON@}" "$PORTAGE_BIN_PATH"/xpak-helper.py recompose \
			"$PORTAGE_BINPKG_TMPFILE" "$PORTAGE_BUILDDIR/build-info"
		# END PREFIX LOCAL
		if [[ $? -ne 0 ]]; then
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
		[[ -n "${md5_hash}" ]] && \
			echo ${md5_hash} > "${PORTAGE_BUILDDIR}"/build-info/BINPKGMD5
		__vecho ">>> Done."

	elif [[ "${BINPKG_FORMAT}" == "gpkg" ]]; then
		# BEGIN PREFIX LOCAL: use PREFIX_PORTAGE_PYTHON fallback
		PYTHONPATH=${PORTAGE_PYTHONPATH:-${PORTAGE_PYM_PATH}} \
			"${PORTAGE_PYTHON:-@PREFIX_PORTAGE_PYTHON@}" "$PORTAGE_BIN_PATH"/gpkg-helper.py compress \
			"${CATEGORY}/${PF}" "$PORTAGE_BINPKG_TMPFILE" "$PORTAGE_BUILDDIR/build-info" "${D}"
		# END PREFIX LOCAL
		if [[ $? -ne 0 ]]; then
			rm -f "${PORTAGE_BINPKG_TMPFILE}"
			die "Failed to create binpkg file"
		fi
		__vecho ">>> Done."
	else
		die "Unknown BINPKG_FORMAT ${BINPKG_FORMAT}"
	fi

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
		if [[ -x "$fp" ]]; then
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

if [[ -n "${MISC_FUNCTIONS_ARGS}" ]]; then
	__source_all_bashrcs
	[[ "$PORTAGE_DEBUG" == "1" ]] && set -x
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
