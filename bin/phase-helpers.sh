#!/bin/bash
# Copyright 1999-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

if ___eapi_has_DESTTREE_INSDESTTREE; then
	export DESTTREE=/usr
	export INSDESTTREE=""
else
	export _E_DESTTREE_=/usr
	export _E_INSDESTTREE_=""
fi
export _E_EXEDESTTREE_=""
export _E_DOCDESTTREE_=""
export INSOPTIONS="-m0644"
export EXEOPTIONS="-m0755"
export LIBOPTIONS="-m0644"
export DIROPTIONS="-m0755"
export MOPREFIX=${PN}
# Do not compress files which are smaller than this (in bytes). #169260
export PORTAGE_DOCOMPRESS_SIZE_LIMIT="128"
declare -a PORTAGE_DOCOMPRESS=( /usr/share/{doc,info,man} )
declare -a PORTAGE_DOCOMPRESS_SKIP=( /usr/share/doc/${PF}/html )
declare -a PORTAGE_DOSTRIP=( / )
has strip ${PORTAGE_RESTRICT} && PORTAGE_DOSTRIP=()
declare -a PORTAGE_DOSTRIP_SKIP=()

into() {
	if [ "$1" == "/" ]; then
		export _E_DESTTREE_=""
	else
		export _E_DESTTREE_=$1
		if ! ___eapi_has_prefix_variables; then
			local ED=${D}
		fi
		if [ ! -d "${ED%/}/${_E_DESTTREE_#/}" ]; then
			install -d "${ED%/}/${_E_DESTTREE_#/}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return $ret
			fi
		fi
	fi

	if ___eapi_has_DESTTREE_INSDESTTREE; then
		export DESTTREE=${_E_DESTTREE_}
	fi
}

insinto() {
	if [ "$1" == "/" ]; then
		export _E_INSDESTTREE_=""
	else
		export _E_INSDESTTREE_=$1
		if ! ___eapi_has_prefix_variables; then
			local ED=${D}
		fi
		if [ ! -d "${ED%/}/${_E_INSDESTTREE_#/}" ]; then
			install -d "${ED%/}/${_E_INSDESTTREE_#/}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return $ret
			fi
		fi
	fi

	if ___eapi_has_DESTTREE_INSDESTTREE; then
		export INSDESTTREE=${_E_INSDESTTREE_}
	fi
}

exeinto() {
	if [ "$1" == "/" ]; then
		export _E_EXEDESTTREE_=""
	else
		export _E_EXEDESTTREE_="$1"
		if ! ___eapi_has_prefix_variables; then
			local ED=${D}
		fi
		if [ ! -d "${ED%/}/${_E_EXEDESTTREE_#/}" ]; then
			install -d "${ED%/}/${_E_EXEDESTTREE_#/}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return $ret
			fi
		fi
	fi
}

docinto() {
	if [ "$1" == "/" ]; then
		export _E_DOCDESTTREE_=""
	else
		export _E_DOCDESTTREE_="$1"
		if ! ___eapi_has_prefix_variables; then
			local ED=${D}
		fi
		if [ ! -d "${ED%/}/usr/share/doc/${PF}/${_E_DOCDESTTREE_#/}" ]; then
			install -d "${ED%/}/usr/share/doc/${PF}/${_E_DOCDESTTREE_#/}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return $ret
			fi
		fi
	fi
}

insopts() {
	export INSOPTIONS="$@"

	# `install` should never be called with '-s' ...
	has -s ${INSOPTIONS} && die "Never call insopts() with -s"
}

diropts() {
	export DIROPTIONS="$@"
}

exeopts() {
	export EXEOPTIONS="$@"

	# `install` should never be called with '-s' ...
	has -s ${EXEOPTIONS} && die "Never call exeopts() with -s"
}

libopts() {
	if ! ___eapi_has_dolib_libopts; then
		die "'${FUNCNAME}' has been banned for EAPI '$EAPI'"
	fi

	export LIBOPTIONS="$@"

	# `install` should never be called with '-s' ...
	has -s ${LIBOPTIONS} && die "Never call libopts() with -s"
}

docompress() {
	___eapi_has_docompress || die "'docompress' not supported in this EAPI"

	local f g
	if [[ $1 = "-x" ]]; then
		shift
		for f; do
			f=$(__strip_duplicate_slashes "${f}"); f=${f%/}
			[[ ${f:0:1} = / ]] || f="/${f}"
			for g in "${PORTAGE_DOCOMPRESS_SKIP[@]}"; do
				[[ ${f} = "${g}" ]] && continue 2
			done
			PORTAGE_DOCOMPRESS_SKIP[${#PORTAGE_DOCOMPRESS_SKIP[@]}]=${f}
		done
	else
		for f; do
			f=$(__strip_duplicate_slashes "${f}"); f=${f%/}
			[[ ${f:0:1} = / ]] || f="/${f}"
			for g in "${PORTAGE_DOCOMPRESS[@]}"; do
				[[ ${f} = "${g}" ]] && continue 2
			done
			PORTAGE_DOCOMPRESS[${#PORTAGE_DOCOMPRESS[@]}]=${f}
		done
	fi
}

dostrip() {
	___eapi_has_dostrip || die "'${FUNCNAME}' not supported in this EAPI"

	local f g
	if [[ $1 = "-x" ]]; then
		shift
		for f; do
			f=$(__strip_duplicate_slashes "${f}"); f=${f%/}
			[[ ${f:0:1} = / ]] || f="/${f}"
			for g in "${PORTAGE_DOSTRIP_SKIP[@]}"; do
				[[ ${f} = "${g}" ]] && continue 2
			done
			PORTAGE_DOSTRIP_SKIP+=( "${f}" )
		done
	else
		for f; do
			f=$(__strip_duplicate_slashes "${f}"); f=${f%/}
			[[ ${f:0:1} = / ]] || f="/${f}"
			for g in "${PORTAGE_DOSTRIP[@]}"; do
				[[ ${f} = "${g}" ]] && continue 2
			done
			PORTAGE_DOSTRIP+=( "${f}" )
		done
	fi
}

useq() {
	___eapi_has_useq || die "'${FUNCNAME}' banned in EAPI ${EAPI}"

	eqawarn "QA Notice: The 'useq' function is deprecated (replaced by 'use')"
	use ${1}
}

usev() {
	local nargs=1
	___eapi_usev_has_second_arg && nargs=2
	[[ ${#} -gt ${nargs} ]] && die "usev takes at most ${nargs} arguments"

	if use ${1}; then
		echo "${2:-${1#!}}"
		return 0
	fi
	return 1
}

if ___eapi_has_usex; then
	usex() {
		if use "$1"; then
			echo "${2-yes}$4"
		else
			echo "${3-no}$5"
		fi
		return 0
	}
fi

use() {
	local u=$1
	local found=0

	# if we got something like '!flag', then invert the return value
	if [[ ${u:0:1} == "!" ]] ; then
		u=${u:1}
		found=1
	fi

	if [[ $EBUILD_PHASE = depend ]] ; then
		# TODO: Add a registration interface for eclasses to register
		# any number of phase hooks, so that global scope eclass
		# initialization can by migrated to phase hooks in new EAPIs.
		# Example: add_phase_hook before pkg_setup $ECLASS_pre_pkg_setup
		#if [[ -n $EAPI ]] && ! has "$EAPI" 0 1 2 3 ; then
		#	die "use() called during invalid phase: $EBUILD_PHASE"
		#fi
		true

	# Make sure we have this USE flag in IUSE, but exempt binary
	# packages for API consumers like Entropy which do not require
	# a full profile with IUSE_IMPLICIT and stuff (see bug #456830).
	elif declare -f ___in_portage_iuse >/dev/null &&
		[[ -n ${EBUILD_PHASE} && -n ${PORTAGE_INTERNAL_CALLER} ]] ; then
		if ! ___in_portage_iuse "${u}"; then
			if [[ ${EMERGE_FROM} != binary &&
				! ${EAPI} =~ ^(0|1|2|3|4|4-python|4-slot-abi)$ ]] ; then
				# This is only strict starting with EAPI 5, since implicit IUSE
				# is not well defined for earlier EAPIs (see bug #449708).
				die "USE Flag '${u}' not in IUSE for ${CATEGORY}/${PF}"
			fi
			eqawarn "QA Notice: USE Flag '${u}' not" \
				"in IUSE for ${CATEGORY}/${PF}"
		fi
	fi

	local IFS=$' \t\n' prev_shopts=$- ret
	set -f
	if has ${u} ${USE} ; then
		ret=${found}
	else
		ret=$((!found))
	fi
	[[ ${prev_shopts} == *f* ]] || set +f
	return ${ret}
}

use_with() {
	if [ -z "$1" ]; then
		echo "!!! use_with() called without a parameter." >&2
		echo "!!! use_with <USEFLAG> [<flagname> [value]]" >&2
		return 1
	fi

	if ___eapi_use_enable_and_use_with_support_empty_third_argument; then
		local UW_SUFFIX=${3+=$3}
	else
		local UW_SUFFIX=${3:+=$3}
	fi
	local UWORD=${2:-$1}

	if use $1; then
		echo "--with-${UWORD}${UW_SUFFIX}"
	else
		echo "--without-${UWORD}"
	fi
	return 0
}

use_enable() {
	if [ -z "$1" ]; then
		echo "!!! use_enable() called without a parameter." >&2
		echo "!!! use_enable <USEFLAG> [<flagname> [value]]" >&2
		return 1
	fi

	if ___eapi_use_enable_and_use_with_support_empty_third_argument; then
		local UE_SUFFIX=${3+=$3}
	else
		local UE_SUFFIX=${3:+=$3}
	fi
	local UWORD=${2:-$1}

	if use $1; then
		echo "--enable-${UWORD}${UE_SUFFIX}"
	else
		echo "--disable-${UWORD}"
	fi
	return 0
}

unpack() {
	local srcdir
	local x
	local y y_insensitive
	local suffix suffix_insensitive
	local myfail
	local eapi=${EAPI:-0}
	[ -z "$*" ] && die "Nothing passed to the 'unpack' command"

	for x in "$@"; do
		__vecho ">>> Unpacking ${x} to ${PWD}"
		suffix=${x##*.}
		suffix_insensitive=$(LC_ALL=C tr "[:upper:]" "[:lower:]" <<< "${suffix}")
		y=${x%.*}
		y=${y##*.}
		y_insensitive=$(LC_ALL=C tr "[:upper:]" "[:lower:]" <<< "${y}")

		# wrt PMS 11.3.3.13 Misc Commands
		if [[ ${x} != */* ]]; then
			# filename without path of any kind
			srcdir=${DISTDIR}/
		elif [[ ${x} == ./* ]]; then
			# relative path starting with './'
			srcdir=
		else
			# non-'./' filename with path of some kind
			if ___eapi_unpack_supports_absolute_paths; then
				# EAPI 6 allows absolute and deep relative paths
				srcdir=

				if [[ ${x} == ${DISTDIR%/}/* ]]; then
					eqawarn "QA Notice: unpack called with redundant \${DISTDIR} in path"
				fi
			elif [[ ${x} == ${DISTDIR%/}/* ]]; then
				die "Arguments to unpack() cannot begin with \${DISTDIR} in EAPI ${EAPI}"
			elif [[ ${x} == /* ]] ; then
				die "Arguments to unpack() cannot be absolute in EAPI ${EAPI}"
			else
				die "Relative paths to unpack() must be prefixed with './' in EAPI ${EAPI}"
			fi
		fi
		[[ ! -s ${srcdir}${x} ]] && die "unpack: ${x} does not exist"

		__unpack_tar() {
			if [[ ${y_insensitive} == tar ]] ; then
				if ___eapi_unpack_is_case_sensitive && \
					[[ tar != ${y} ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"secondary suffix '${y}' which is unofficially" \
						"supported with EAPI '${EAPI}'. Instead use 'tar'."
				fi
				$1 -c -- "$srcdir$x" | tar xof -
				__assert_sigpipe_ok "$myfail"
			else
				local cwd_dest=${x##*/}
				cwd_dest=${cwd_dest%.*}
				$1 -c -- "${srcdir}${x}" > "${cwd_dest}" || die "$myfail"
			fi
		}

		myfail="unpack: failure unpacking ${x}"
		case "${suffix_insensitive}" in
			tar)
				if ___eapi_unpack_is_case_sensitive && \
					[[ tar != ${suffix} ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'tar'."
				fi
				tar xof "$srcdir$x" || die "$myfail"
				;;
			tgz)
				if ___eapi_unpack_is_case_sensitive && \
					[[ tgz != ${suffix} ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'tgz'."
				fi
				tar xozf "$srcdir$x" || die "$myfail"
				;;
			tbz|tbz2)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " tbz tbz2 " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'tbz' or 'tbz2'."
				fi
				${PORTAGE_BUNZIP2_COMMAND:-${PORTAGE_BZIP2_COMMAND} -d} -c -- "$srcdir$x" | tar xof -
				__assert_sigpipe_ok "$myfail"
				;;
			zip|jar)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " ZIP zip jar " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'." \
						"Instead use 'ZIP', 'zip', or 'jar'."
				fi
				# unzip will interactively prompt under some error conditions,
				# as reported in bug #336285
				( set +x ; while true ; do echo n || break ; done ) | \
				unzip -qo "${srcdir}${x}" || die "$myfail"
				;;
			gz|z)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " gz z Z " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'gz', 'z', or 'Z'."
				fi
				__unpack_tar "gzip -d"
				;;
			bz2|bz)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " bz bz2 " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'bz' or 'bz2'."
				fi
				__unpack_tar "${PORTAGE_BUNZIP2_COMMAND:-${PORTAGE_BZIP2_COMMAND} -d}"
				;;
			7z)
				if ___eapi_unpack_supports_7z; then
					local my_output
					my_output="$(7z x -y "${srcdir}${x}")"
					if [ $? -ne 0 ]; then
						echo "${my_output}" >&2
						die "$myfail"
					fi
				else
					__vecho "unpack ${x}: file format not recognized. Ignoring."
				fi
				;;
			rar)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " rar RAR " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'rar' or 'RAR'."
				fi
				if ___eapi_unpack_supports_rar; then
					unrar x -idq -o+ "${srcdir}${x}" || die "$myfail"
				else
					__vecho "unpack ${x}: file format not recognized. Ignoring."
				fi
				;;
			lha|lzh)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " LHA LHa lha lzh " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'." \
						"Instead use 'LHA', 'LHa', 'lha', or 'lzh'."
				fi
				if ___eapi_unpack_supports_lha; then
					lha xfq "${srcdir}${x}" || die "$myfail"
				else
					__vecho "unpack ${x}: file format not recognized. Ignoring."
				fi
				;;
			a)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " a " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'a'."
				fi
				ar x "${srcdir}${x}" || die "$myfail"
				;;
			deb)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " deb " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'deb'."
				fi
				# Unpacking .deb archives can not always be done with
				# `ar`.  For instance on AIX this doesn't work out.
				# If `ar` is not the GNU binutils version and we have
				# `deb2targz` installed, prefer it over `ar` for that
				# reason.  We just make sure on AIX `deb2targz` is
				# installed.
				if [[ $(ar --version 2>/dev/null) != "GNU ar"* ]] && \
					type -P deb2targz > /dev/null; then
					y=${x##*/}
					local created_symlink=0
					if [ ! "$srcdir$x" -ef "$y" ] ; then
						# deb2targz always extracts into the same directory as
						# the source file, so create a symlink in the current
						# working directory if necessary.
						ln -sf "$srcdir$x" "$y" || die "$myfail"
						created_symlink=1
					fi
					deb2targz "$y" || die "$myfail"
					if [ $created_symlink = 1 ] ; then
						# Clean up the symlink so the ebuild
						# doesn't inadvertently install it.
						rm -f "$y"
					fi
					mv -f "${y%.deb}".tar.gz data.tar.gz \
						|| mv -f "${y%.deb}".tar.xz data.tar.xz \
						|| die "$myfail"
				else
					ar x "$srcdir$x" || die "$myfail"
				fi
				;;
			lzma)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " lzma " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'lzma'."
				fi
				__unpack_tar "lzma -d"
				;;
			xz)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " xz " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'xz'."
				fi
				if ___eapi_unpack_supports_xz; then
					__unpack_tar "xz -d"
				else
					__vecho "unpack ${x}: file format not recognized. Ignoring."
				fi
				;;
			txz)
				if ___eapi_unpack_is_case_sensitive && \
					[[ " txz " != *" ${suffix} "* ]] ; then
					eqawarn "QA Notice: unpack called with" \
						"suffix '${suffix}' which is unofficially supported" \
						"with EAPI '${EAPI}'. Instead use 'txz'."
				fi
				if ___eapi_unpack_supports_txz; then
					tar xof "$srcdir$x" || die "$myfail"
				else
					__vecho "unpack ${x}: file format not recognized. Ignoring."
				fi
				;;
			*)
				__vecho "unpack ${x}: file format not recognized. Ignoring."
				;;
		esac
	done
	# Do not chmod '.' since it's probably ${WORKDIR} and PORTAGE_WORKDIR_MODE
	# should be preserved.
	find . -mindepth 1 -maxdepth 1 ! -type l -print0 | \
		${XARGS} -0 "${PORTAGE_BIN_PATH}/chmod-lite"
}

econf() {
	local x
	local pid=${BASHPID:-$(__bashpid)}

	if ! ___eapi_has_prefix_variables; then
		local EPREFIX=
	fi

	__hasg() {
		local x s=$1
		shift
		for x ; do [[ ${x} == ${s} ]] && echo "${x}" && return 0 ; done
		return 1
	}

	__hasgq() { __hasg "$@" >/dev/null ; }

	local phase_func=$(__ebuild_arg_to_phase "$EBUILD_PHASE")
	if [[ -n $phase_func ]] ; then
		if ! ___eapi_has_src_configure; then
			[[ $phase_func != src_compile ]] && \
				eqawarn "QA Notice: econf called in" \
					"$phase_func instead of src_compile"
		else
			[[ $phase_func != src_configure ]] && \
				eqawarn "QA Notice: econf called in" \
					"$phase_func instead of src_configure"
		fi
	fi

	: ${ECONF_SOURCE:=.}
	if [ -x "${ECONF_SOURCE}/configure" ]; then
		if [[ -n $CONFIG_SHELL && \
			"$(head -n1 "$ECONF_SOURCE/configure")" =~ ^'#!'[[:space:]]*/bin/sh([[:space:]]|$) ]] ; then
			cp -p "${ECONF_SOURCE}/configure" "${ECONF_SOURCE}/configure._portage_tmp_.${pid}" || die
			sed -i \
				-e "1s:^#![[:space:]]*/bin/sh:#!$CONFIG_SHELL:" \
				"${ECONF_SOURCE}/configure._portage_tmp_.${pid}" \
				|| die "Substition of shebang in '${ECONF_SOURCE}/configure' failed"
			# preserve timestamp, see bug #440304
			touch -r "${ECONF_SOURCE}/configure" "${ECONF_SOURCE}/configure._portage_tmp_.${pid}" || die
			mv -f "${ECONF_SOURCE}/configure._portage_tmp_.${pid}" "${ECONF_SOURCE}/configure" || die
		fi
		if [ -e "${EPREFIX}"/usr/share/gnuconfig/ ]; then
			find "${WORKDIR}" -type f '(' \
			-name config.guess -o -name config.sub ')' -print0 | \
			while read -r -d $'\0' x ; do
				__vecho " * econf: updating ${x/${WORKDIR}\/} with ${EPREFIX}/usr/share/gnuconfig/${x##*/}"
				# Make sure we do this atomically incase we're run in parallel. #487478
				cp -f "${EPREFIX}"/usr/share/gnuconfig/"${x##*/}" "${x}.${pid}"
				mv -f "${x}.${pid}" "${x}"
			done
		fi

		local conf_args=()
		if ___eapi_econf_passes_--disable-dependency-tracking || ___eapi_econf_passes_--disable-silent-rules || ___eapi_econf_passes_--docdir_and_--htmldir || ___eapi_econf_passes_--with-sysroot; then
			local conf_help=$("${ECONF_SOURCE}/configure" --help 2>/dev/null)

			if ___eapi_econf_passes_--datarootdir; then
				if [[ ${conf_help} == *--datarootdir* ]]; then
					conf_args+=( --datarootdir="${EPREFIX}"/usr/share )
				fi
			fi

			if ___eapi_econf_passes_--disable-dependency-tracking; then
				if [[ ${conf_help} == *--disable-dependency-tracking* ]]; then
					conf_args+=( --disable-dependency-tracking )
				fi
			fi

			if ___eapi_econf_passes_--disable-silent-rules; then
				if [[ ${conf_help} == *--disable-silent-rules* ]]; then
					conf_args+=( --disable-silent-rules )
				fi
			fi

			if ___eapi_econf_passes_--disable-static; then
				if [[ ${conf_help} == *--disable-static* || \
						${conf_help} == *--enable-static* ]]; then
					conf_args+=( --disable-static )
				fi
			fi

			if ___eapi_econf_passes_--docdir_and_--htmldir; then
				if [[ ${conf_help} == *--docdir* ]]; then
					conf_args+=( --docdir="${EPREFIX}"/usr/share/doc/${PF} )
				fi

				if [[ ${conf_help} == *--htmldir* ]]; then
					conf_args+=( --htmldir="${EPREFIX}"/usr/share/doc/${PF}/html )
				fi
			fi

			if ___eapi_econf_passes_--with-sysroot; then
				if [[ ${conf_help} == *--with-sysroot* ]]; then
					conf_args+=( --with-sysroot="${ESYSROOT:-/}" )
				fi
			fi
		fi

		# if the profile defines a location to install libs to aside from default, pass it on.
		# if the ebuild passes in --libdir, they're responsible for the conf_libdir fun.
		local CONF_LIBDIR LIBDIR_VAR="LIBDIR_${ABI}"
		if [[ -n ${ABI} && -n ${!LIBDIR_VAR} ]] ; then
			CONF_LIBDIR=${!LIBDIR_VAR}
		fi
		if [[ -n ${CONF_LIBDIR} ]] && ! __hasgq --libdir=\* "$@" ; then
			export CONF_PREFIX=$(__hasg --exec-prefix=\* "$@")
			[[ -z ${CONF_PREFIX} ]] && CONF_PREFIX=$(__hasg --prefix=\* "$@")
			: ${CONF_PREFIX:=${EPREFIX}/usr}
			CONF_PREFIX=${CONF_PREFIX#*=}
			[[ ${CONF_PREFIX} != /* ]] && CONF_PREFIX="/${CONF_PREFIX}"
			[[ ${CONF_LIBDIR} != /* ]] && CONF_LIBDIR="/${CONF_LIBDIR}"
			conf_args+=(
				--libdir="$(__strip_duplicate_slashes "${CONF_PREFIX}${CONF_LIBDIR}")"
			)
		fi

		# Handle arguments containing quoted whitespace (see bug #457136).
		eval "local -a EXTRA_ECONF=(${EXTRA_ECONF})"

		set -- \
			--prefix="${EPREFIX}"/usr \
			${CBUILD:+--build=${CBUILD}} \
			--host=${CHOST} \
			${CTARGET:+--target=${CTARGET}} \
			--mandir="${EPREFIX}"/usr/share/man \
			--infodir="${EPREFIX}"/usr/share/info \
			--datadir="${EPREFIX}"/usr/share \
			--sysconfdir="${EPREFIX}"/etc \
			--localstatedir="${EPREFIX}"/var/lib \
			"${conf_args[@]}" \
			"$@" \
			"${EXTRA_ECONF[@]}"
		__vecho "${ECONF_SOURCE}/configure" "$@"

		if ! "${ECONF_SOURCE}/configure" "$@" ; then

			if [ -s config.log ]; then
				echo
				echo "!!! Please attach the following file when seeking support:"
				echo "!!! ${PWD}/config.log"
			fi
			# econf dies unconditionally in EAPIs 0 to 3
			___eapi_helpers_can_die || die "econf failed"
			__helpers_die "econf failed"
			return 1
		fi
	elif [ -f "${ECONF_SOURCE}/configure" ]; then
		die "configure is not executable"
	else
		die "no configure script found"
	fi
}

einstall() {
	if ! ___eapi_has_einstall; then
		die "'${FUNCNAME}' has been banned for EAPI '$EAPI'"
		exit 1
	fi

	# CONF_PREFIX is only set if they didn't pass in libdir above.
	local LOCAL_EXTRA_EINSTALL="${EXTRA_EINSTALL}"
	if ! ___eapi_has_prefix_variables; then
		local ED=${D}
	fi
	LIBDIR_VAR="LIBDIR_${ABI}"
	if [ -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
		CONF_LIBDIR="${!LIBDIR_VAR}"
	fi
	unset LIBDIR_VAR
	if [ -n "${CONF_LIBDIR}" ] && [ "${CONF_PREFIX:+set}" = set ]; then
		EI_DESTLIBDIR="${D%/}/${CONF_PREFIX}/${CONF_LIBDIR}"
		EI_DESTLIBDIR="$(__strip_duplicate_slashes "${EI_DESTLIBDIR}")"
		LOCAL_EXTRA_EINSTALL="libdir=${EI_DESTLIBDIR} ${LOCAL_EXTRA_EINSTALL}"
		unset EI_DESTLIBDIR
	fi

	if [[ -f Makefile || -f GNUmakefile || -f makefile ]] ; then
		if [ "${PORTAGE_DEBUG}" == "1" ]; then
			${MAKE:-make} -n prefix="${ED%/}/usr" \
				datadir="${ED%/}/usr/share" \
				infodir="${ED%/}/usr/share/info" \
				localstatedir="${ED%/}/var/lib" \
				mandir="${ED%/}/usr/share/man" \
				sysconfdir="${ED%/}/etc" \
				${LOCAL_EXTRA_EINSTALL} \
				${MAKEOPTS} -j1 \
				"$@" ${EXTRA_EMAKE} install
		fi
		if ! ${MAKE:-make} prefix="${ED%/}/usr" \
			datadir="${ED%/}/usr/share" \
			infodir="${ED%/}/usr/share/info" \
			localstatedir="${ED%/}/var/lib" \
			mandir="${ED%/}/usr/share/man" \
			sysconfdir="${ED%/}/etc" \
			${LOCAL_EXTRA_EINSTALL} \
			${MAKEOPTS} -j1 \
			"$@" ${EXTRA_EMAKE} install
		then
			__helpers_die "einstall failed"
			return 1
		fi
	else
		die "no Makefile found"
	fi
}

__eapi0_pkg_nofetch() {
	[[ -z ${A} ]] && return

	elog "The following files cannot be fetched for ${PN}:"
	local x
	for x in ${A}; do
		elog "   ${x}"
	done
}

__eapi0_src_unpack() {
	[[ -n ${A} ]] && unpack ${A}
}

__eapi0_src_compile() {
	if [ -x ./configure ] ; then
		econf
	fi
	__eapi2_src_compile
}

__eapi0_src_test() {
	# Since we don't want emake's automatic die
	# support (EAPI 4 and later), and we also don't
	# want the warning messages that it produces if
	# we call it in 'nonfatal' mode, we use emake_cmd
	# to emulate the desired parts of emake behavior.
	local emake_cmd="${MAKE:-make} ${MAKEOPTS} ${EXTRA_EMAKE}"
	local internal_opts=
	if ___eapi_default_src_test_disables_parallel_jobs; then
		internal_opts+=" -j1"
	fi
	if $emake_cmd ${internal_opts} check -n &> /dev/null; then
		__vecho "${emake_cmd} ${internal_opts} check" >&2
		$emake_cmd ${internal_opts} check || \
			die "Make check failed. See above for details."
	elif $emake_cmd ${internal_opts} test -n &> /dev/null; then
		__vecho "${emake_cmd} ${internal_opts} test" >&2
		$emake_cmd ${internal_opts} test || \
			die "Make test failed. See above for details."
	fi
}

__eapi1_src_compile() {
	__eapi2_src_configure
	__eapi2_src_compile
}

__eapi2_src_prepare() {
	:
}

__eapi2_src_configure() {
	if [[ -x ${ECONF_SOURCE:-.}/configure ]] ; then
		econf
	fi
}

__eapi2_src_compile() {
	if [ -f Makefile ] || [ -f GNUmakefile ] || [ -f makefile ]; then
		emake || die "emake failed"
	fi
}

__eapi4_src_install() {
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]] ; then
		emake DESTDIR="${D}" install
	fi

	if ! declare -p DOCS &>/dev/null ; then
		local d
		for d in README* ChangeLog AUTHORS NEWS TODO CHANGES \
				THANKS BUGS FAQ CREDITS CHANGELOG ; do
			[[ -s "${d}" ]] && dodoc "${d}"
		done
	elif ___is_indexed_array_var DOCS ; then
		dodoc "${DOCS[@]}"
	else
		dodoc ${DOCS}
	fi
}

__eapi6_src_prepare() {
	if ___is_indexed_array_var PATCHES ; then
		[[ ${#PATCHES[@]} -gt 0 ]] && eapply "${PATCHES[@]}"
	elif [[ -n ${PATCHES} ]]; then
		eapply ${PATCHES}
	fi

	eapply_user
}

__eapi6_src_install() {
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]] ; then
		emake DESTDIR="${D}" install
	fi

	einstalldocs
}

__eapi8_src_prepare() {
	local f
	if ___is_indexed_array_var PATCHES ; then
		[[ ${#PATCHES[@]} -gt 0 ]] && eapply -- "${PATCHES[@]}"
	elif [[ -n ${PATCHES} ]]; then
		eapply -- ${PATCHES}
	fi

	eapply_user
}

___best_version_and_has_version_common() {
	local atom root root_arg
	local -a cmd=()
	case $1 in
		--host-root|-r|-d|-b)
			root_arg=$1
			shift ;;
	esac
	atom=$1
	shift
	[ $# -gt 0 ] && die "${FUNCNAME[1]}: unused argument(s): $*"

	case ${root_arg} in
		"") if ___eapi_has_prefix_variables; then
				root=${ROOT%/}/${EPREFIX#/}
			else
				root=${ROOT}
			fi ;;
		--host-root)
			if ! ___eapi_best_version_and_has_version_support_--host-root; then
				die "${FUNCNAME[1]}: option ${root_arg} is not supported with EAPI ${EAPI}"
			fi
			if ___eapi_has_prefix_variables; then
				# Since portageq requires the root argument be consistent
				# with EPREFIX, ensure consistency here (bug 655414).
				root=/${PORTAGE_OVERRIDE_EPREFIX#/}
				cmd+=(env EPREFIX="${PORTAGE_OVERRIDE_EPREFIX}")
			else
				root=/
			fi ;;
		-r|-d|-b)
			if ! ___eapi_best_version_and_has_version_support_-b_-d_-r; then
				die "${FUNCNAME[1]}: option ${root_arg} is not supported with EAPI ${EAPI}"
			fi
			if ___eapi_has_prefix_variables; then
				case ${root_arg} in
					-r) root=${ROOT%/}/${EPREFIX#/} ;;
					-d) root=${ESYSROOT:-/} ;;
					-b)
						# Use /${PORTAGE_OVERRIDE_EPREFIX#/} which is equivalent
						# to BROOT, except BROOT is only defined in src_* phases.
						root=/${PORTAGE_OVERRIDE_EPREFIX#/}
						cmd+=(env EPREFIX="${PORTAGE_OVERRIDE_EPREFIX}")
						;;
				esac
			else
				case ${root_arg} in
					-r) root=${ROOT:-/} ;;
					-d) root=${SYSROOT:-/} ;;
					-b) root=/ ;;
				esac
			fi ;;
	esac

	if [[ -n $PORTAGE_IPC_DAEMON ]] ; then
		cmd+=("${PORTAGE_BIN_PATH}"/ebuild-ipc "${FUNCNAME[1]}" "${root}" "${atom}")
	else
		cmd+=("${PORTAGE_BIN_PATH}"/ebuild-helpers/portageq "${FUNCNAME[1]}" "${root}" "${atom}")
	fi
	"${cmd[@]}"
	local retval=$?
	case "${retval}" in
		0|1)
			return ${retval}
			;;
		2)
			die "${FUNCNAME[1]}: invalid atom: ${atom}"
			;;
		*)
			if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
				die "${FUNCNAME[1]}: unexpected ebuild-ipc exit code: ${retval}"
			else
				die "${FUNCNAME[1]}: unexpected portageq exit code: ${retval}"
			fi
			;;
	esac
}

# @FUNCTION: has_version
# @USAGE: [--host-root|-r|-d|-b] <DEPEND ATOM>
# @DESCRIPTION:
# Return true if given package is installed. Otherwise return false.
# Callers may override the ROOT variable in order to match packages from an
# alternative ROOT.
has_version() {
	___best_version_and_has_version_common "$@"
}

# @FUNCTION: best_version
# @USAGE: [--host-root|-r|-d|-b] <DEPEND ATOM>
# @DESCRIPTION:
# Returns highest installed matching category/package-version (without .ebuild).
# Callers may override the ROOT variable in order to match packages from an
# alternative ROOT.
best_version() {
	___best_version_and_has_version_common "$@"
}

if ___eapi_has_get_libdir; then
	get_libdir() {
		local libdir_var="LIBDIR_${ABI}"
		local libdir="lib"

		[[ -n ${ABI} && -n ${!libdir_var} ]] && libdir=${!libdir_var}

		echo "${libdir}"
	}
fi

if ___eapi_has_einstalldocs; then
	einstalldocs() {
		(
			if [[ $(declare -p DOCS 2>/dev/null) != *=* ]]; then
				local d
				for d in README* ChangeLog AUTHORS NEWS TODO CHANGES \
						THANKS BUGS FAQ CREDITS CHANGELOG ; do
					[[ -f ${d} && -s ${d} ]] && docinto / && dodoc "${d}"
				done
			elif ___is_indexed_array_var DOCS ; then
				[[ ${#DOCS[@]} -gt 0 ]] && docinto / && dodoc -r "${DOCS[@]}"
			else
				[[ ${DOCS} ]] && docinto / && dodoc -r ${DOCS}
			fi
		)

		(
			if ___is_indexed_array_var HTML_DOCS ; then
				[[ ${#HTML_DOCS[@]} -gt 0 ]] && \
					docinto html && dodoc -r "${HTML_DOCS[@]}"
			else
				[[ ${HTML_DOCS} ]] && \
					docinto html && dodoc -r ${HTML_DOCS}
			fi
		)
	}
fi

if ___eapi_has_eapply; then
	eapply() {
		local failed patch_cmd=patch
		local -x LC_COLLATE=POSIX

		# for bsd userland support, use gpatch if available
		type -P gpatch > /dev/null && patch_cmd=gpatch

		_eapply_patch() {
			local f=${1}
			local prefix=${2}

			ebegin "${prefix:-Applying }${f##*/}"
			# -p1 as a sane default
			# -f to avoid interactivity
			# -g0 to guarantee no VCS interaction
			# --no-backup-if-mismatch not to pollute the sources
			local all_opts=(
				-p1 -f -g0 --no-backup-if-mismatch
				"${patch_options[@]}"
			)
			# try applying with -F0 first, output a verbose warning
			# if fuzz factor is necessary
			if ${patch_cmd} "${all_opts[@]}" --dry-run -s -F0 \
					< "${f}" &>/dev/null; then
				all_opts+=( -s -F0 )
			fi

			${patch_cmd} "${all_opts[@]}" < "${f}"
			failed=${?}
			if ! eend "${failed}"; then
				__helpers_die "patch -p1 ${patch_options[*]} failed with ${f}"
			fi
		}

		local patch_options=() files=()
		local i found_doublehyphen
		# first, try to split on --
		for (( i = 1; i <= ${#@}; ++i )); do
			if [[ ${@:i:1} == -- ]]; then
				patch_options=( "${@:1:i-1}" )
				files=( "${@:i+1}" )
				found_doublehyphen=1
				break
			fi
		done

		# then, try to split on first non-option
		if [[ -z ${found_doublehyphen} ]]; then
			for (( i = 1; i <= ${#@}; ++i )); do
				if [[ ${@:i:1} != -* ]]; then
					patch_options=( "${@:1:i-1}" )
					files=( "${@:i}" )
					break
				fi
			done

			# ensure that no options were interspersed with files
			for i in "${files[@]}"; do
				if [[ ${i} == -* ]]; then
					die "eapply: all options must be passed before non-options"
				fi
			done
		fi

		if [[ ${#files[@]} -eq 0 ]]; then
			die "eapply: no files specified"
		fi

		local f
		for f in "${files[@]}"; do
			if [[ -d ${f} ]]; then
				_eapply_get_files() {
					local LC_ALL=POSIX
					local prev_shopt=$(shopt -p nullglob)
					shopt -s nullglob
					local f
					for f in "${1}"/*; do
						if [[ ${f} == *.diff || ${f} == *.patch ]]; then
							files+=( "${f}" )
						fi
					done
					${prev_shopt}
				}

				local files=()
				_eapply_get_files "${f}"
				[[ ${#files[@]} -eq 0 ]] && die "No *.{patch,diff} files in directory ${f}"

				einfo "Applying patches from ${f} ..."
				local f2
				for f2 in "${files[@]}"; do
					_eapply_patch "${f2}" '  '

					# in case of nonfatal
					[[ ${failed} -ne 0 ]] && return "${failed}"
				done
			else
				_eapply_patch "${f}"

				# in case of nonfatal
				[[ ${failed} -ne 0 ]] && return "${failed}"
			fi
		done

		return 0
	}
fi

if ___eapi_has_eapply_user; then
	eapply_user() {
		[[ ${EBUILD_PHASE} == prepare ]] || \
			die "eapply_user() called during invalid phase: ${EBUILD_PHASE}"
		# keep path in __dyn_prepare in sync!
		local tagfile=${T}/.portage_user_patches_applied
		[[ -f ${tagfile} ]] && return
		>> "${tagfile}"

		local basedir=${PORTAGE_CONFIGROOT%/}/etc/portage/patches

		local columns=${COLUMNS:-0}
		[[ ${columns} == 0 ]] && columns=$(set -- $( ( stty size </dev/tty ) 2>/dev/null || echo 24 80 ) ; echo $2)
		(( columns > 0 )) || (( columns = 80 ))

		local applied d f
		local -A _eapply_user_patches
		local prev_shopt=$(shopt -p nullglob)
		shopt -s nullglob

		# Patches from all matched directories are combined into a
		# sorted (POSIX order) list of the patch basenames. Patches
		# in more-specific directories override patches of the same
		# basename found in less-specific directories. An empty patch
		# (or /dev/null symlink) negates a patch with the same
		# basename found in a less-specific directory.
		#
		# order of specificity:
		# 1. ${CATEGORY}/${P}-${PR} (note: -r0 desired to avoid applying
		#    ${P} twice)
		# 2. ${CATEGORY}/${P}
		# 3. ${CATEGORY}/${PN}
		# all of the above may be optionally followed by a slot
		for d in "${basedir}"/${CATEGORY}/{${P}-${PR},${P},${PN}}{:${SLOT%/*},}; do
			for f in "${d}"/*; do
				if [[ ( ${f} == *.diff || ${f} == *.patch ) &&
					-z ${_eapply_user_patches[${f##*/}]} ]]; then
					_eapply_user_patches[${f##*/}]=${f}
				fi
			done
		done

		if [[ ${#_eapply_user_patches[@]} -gt 0 ]]; then
			while read -r -d '' f; do
				f=${_eapply_user_patches[${f}]}
				if [[ -s ${f} ]]; then
					if [[ -z ${applied} ]]; then
						einfo "${PORTAGE_COLOR_INFO}$(for ((column = 0; column < ${columns} - 3; column++)); do echo -n =; done)${PORTAGE_COLOR_NORMAL}"
						einfo "Applying user patches from ${basedir} ..."
					fi

					eapply "${f}"
					applied=1
				fi
			done < <(printf -- '%s\0' "${!_eapply_user_patches[@]}" |
				LC_ALL=C sort -z)
		fi

		${prev_shopt}

		if [[ -n ${applied} ]]; then
			einfo "User patches applied."
			einfo "${PORTAGE_COLOR_INFO}$(for ((column = 0; column < ${columns} - 3; column++)); do echo -n =; done)${PORTAGE_COLOR_NORMAL}"
		fi
	}
fi

if ___eapi_has_in_iuse; then
	in_iuse() {
		local use=${1}

		if [[ -z "${use}" ]]; then
			echo "!!! in_iuse() called without a parameter." >&2
			echo "!!! in_iuse <USEFLAG>" >&2
			die "in_iuse() called without a parameter"
		fi

		local liuse=( ${IUSE_EFFECTIVE} )

		has "${use}" "${liuse[@]#[+-]}"
	}
fi

if ___eapi_has_master_repositories; then
	master_repositories() {
		local output repository=$1 retval
		shift
		[[ $# -gt 0 ]] && die "${FUNCNAME[0]}: unused argument(s): $*"

		if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
			"${PORTAGE_BIN_PATH}/ebuild-ipc" master_repositories "${EROOT}" "${repository}"
		else
			output=$("${PORTAGE_BIN_PATH}/ebuild-helpers/portageq" master_repositories "${EROOT}" "${repository}")
		fi
		retval=$?
		[[ -n ${output} ]] && echo "${output}"
		case "${retval}" in
			0|1)
				return ${retval}
				;;
			2)
				die "${FUNCNAME[0]}: invalid repository: ${repository}"
				;;
			*)
				if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
					die "${FUNCNAME[0]}: unexpected ebuild-ipc exit code: ${retval}"
				else
					die "${FUNCNAME[0]}: unexpected portageq exit code: ${retval}"
				fi
				;;
		esac
	}
fi

if ___eapi_has_repository_path; then
	repository_path() {
		local output repository=$1 retval
		shift
		[[ $# -gt 0 ]] && die "${FUNCNAME[0]}: unused argument(s): $*"

		if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
			"${PORTAGE_BIN_PATH}/ebuild-ipc" repository_path "${EROOT}" "${repository}"
		else
			output=$("${PORTAGE_BIN_PATH}/ebuild-helpers/portageq" get_repo_path "${EROOT}" "${repository}")
		fi
		retval=$?
		[[ -n ${output} ]] && echo "${output}"
		case "${retval}" in
			0|1)
				return ${retval}
				;;
			2)
				die "${FUNCNAME[0]}: invalid repository: ${repository}"
				;;
			*)
				if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
					die "${FUNCNAME[0]}: unexpected ebuild-ipc exit code: ${retval}"
				else
					die "${FUNCNAME[0]}: unexpected portageq exit code: ${retval}"
				fi
				;;
		esac
	}
fi

if ___eapi_has_available_eclasses; then
	available_eclasses() {
		local output repository=${PORTAGE_REPO_NAME} retval
		[[ $# -gt 0 ]] && die "${FUNCNAME[0]}: unused argument(s): $*"

		if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
			"${PORTAGE_BIN_PATH}/ebuild-ipc" available_eclasses "${EROOT}" "${repository}"
		else
			output=$("${PORTAGE_BIN_PATH}/ebuild-helpers/portageq" available_eclasses "${EROOT}" "${repository}")
		fi
		retval=$?
		[[ -n ${output} ]] && echo "${output}"
		case "${retval}" in
			0|1)
				return ${retval}
				;;
			2)
				die "${FUNCNAME[0]}: invalid repository: ${repository}"
				;;
			*)
				if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
					die "${FUNCNAME[0]}: unexpected ebuild-ipc exit code: ${retval}"
				else
					die "${FUNCNAME[0]}: unexpected portageq exit code: ${retval}"
				fi
				;;
		esac
	}
fi

if ___eapi_has_eclass_path; then
	eclass_path() {
		local eclass=$1 output repository=${PORTAGE_REPO_NAME} retval
		shift
		[[ $# -gt 0 ]] && die "${FUNCNAME[0]}: unused argument(s): $*"

		if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
			"${PORTAGE_BIN_PATH}/ebuild-ipc" eclass_path "${EROOT}" "${repository}" "${eclass}"
		else
			output=$("${PORTAGE_BIN_PATH}/ebuild-helpers/portageq" eclass_path "${EROOT}" "${repository}" "${eclass}")
		fi
		retval=$?
		[[ -n ${output} ]] && echo "${output}"
		case "${retval}" in
			0|1)
				return ${retval}
				;;
			2)
				die "${FUNCNAME[0]}: invalid repository: ${repository}"
				;;
			*)
				if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
					die "${FUNCNAME[0]}: unexpected ebuild-ipc exit code: ${retval}"
				else
					die "${FUNCNAME[0]}: unexpected portageq exit code: ${retval}"
				fi
				;;
		esac
	}
fi

if ___eapi_has_license_path; then
	license_path() {
		local license=$1 output repository=${PORTAGE_REPO_NAME} retval
		shift
		[[ $# -gt 0 ]] && die "${FUNCNAME[0]}: unused argument(s): $*"

		if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
			"${PORTAGE_BIN_PATH}/ebuild-ipc" license_path "${EROOT}" "${repository}" "${license}"
		else
			output=$("${PORTAGE_BIN_PATH}/ebuild-helpers/portageq" license_path "${EROOT}" "${repository}" "${license}")
		fi
		retval=$?
		[[ -n ${output} ]] && echo "${output}"
		case "${retval}" in
			0|1)
				return ${retval}
				;;
			2)
				die "${FUNCNAME[0]}: invalid repository: ${repository}"
				;;
			*)
				if [[ -n ${PORTAGE_IPC_DAEMON} ]]; then
					die "${FUNCNAME[0]}: unexpected ebuild-ipc exit code: ${retval}"
				else
					die "${FUNCNAME[0]}: unexpected portageq exit code: ${retval}"
				fi
				;;
		esac
	}
fi

if ___eapi_has_package_manager_build_user; then
	package_manager_build_user() {
		echo "${PORTAGE_BUILD_USER}"
	}
fi

if ___eapi_has_package_manager_build_group; then
	package_manager_build_group() {
		echo "${PORTAGE_BUILD_GROUP}"
	}
fi
