#!/usr/bin/env bash
# Copyright 1999-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# shellcheck disable=2128,2188

if ___eapi_has_DESTTREE_INSDESTTREE; then
	export DESTTREE=/usr
	export INSDESTTREE=""
else
	export __E_DESTTREE=/usr
	export __E_INSDESTTREE=""
fi
export __E_EXEDESTTREE=""
export __E_DOCDESTTREE=""
export INSOPTIONS="-m0644"
export EXEOPTIONS="-m0755"
export LIBOPTIONS="-m0644"
export DIROPTIONS="-m0755"
export MOPREFIX=${PN}
# Do not compress files which are smaller than this (in bytes), bug #169260
export PORTAGE_DOCOMPRESS_SIZE_LIMIT="128"
declare -a PORTAGE_DOCOMPRESS=( /usr/share/{doc,info,man} )
declare -a PORTAGE_DOCOMPRESS_SKIP=( "/usr/share/doc/${PF}/html" )
declare -a PORTAGE_DOSTRIP=()
declare -a PORTAGE_DOSTRIP_SKIP=()

if ! contains_word strip "${PORTAGE_RESTRICT}"; then
        PORTAGE_DOSTRIP+=( / )
fi

into() {
	if [[ "$1" == "/" ]]; then
		export __E_DESTTREE=""
	else
		export __E_DESTTREE=$1
		if ! ___eapi_has_prefix_variables; then
			local ED=${D}
		fi
		if [[ ! -d "${ED%/}/${__E_DESTTREE#/}" ]]; then
			install -d "${ED%/}/${__E_DESTTREE#/}"

			local ret=$?
			if [[ ${ret} -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return ${ret}
			fi
		fi
	fi

	if ___eapi_has_DESTTREE_INSDESTTREE; then
		export DESTTREE=${__E_DESTTREE}
	fi
}

insinto() {
	if [[ "${1}" == "/" ]]; then
		export __E_INSDESTTREE=""
	else
		export __E_INSDESTTREE=${1}
		if ! ___eapi_has_prefix_variables; then
			local ED=${D}
		fi
		if [[ ! -d "${ED%/}/${__E_INSDESTTREE#/}" ]]; then
			install -d "${ED%/}/${__E_INSDESTTREE#/}"

			local ret=$?
			if [[ ${ret} -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return ${ret}
			fi
		fi
	fi

	if ___eapi_has_DESTTREE_INSDESTTREE; then
		export INSDESTTREE=${__E_INSDESTTREE}
	fi
}

exeinto() {
	if [[ "${1}" == "/" ]]; then
		export __E_EXEDESTTREE=""
	else
		export __E_EXEDESTTREE="${1}"
		if ! ___eapi_has_prefix_variables; then
			local ED=${D}
		fi
		if [[ ! -d "${ED%/}/${__E_EXEDESTTREE#/}" ]]; then
			install -d "${ED%/}/${__E_EXEDESTTREE#/}"

			local ret=$?
			if [[ ${ret} -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return ${ret}
			fi
		fi
	fi
}

docinto() {
	if [[ "${1}" == "/" ]]; then
		export __E_DOCDESTTREE=""
	else
		export __E_DOCDESTTREE="${1}"
		if ! ___eapi_has_prefix_variables; then
			local ED=${D}
		fi
		if [[ ! -d "${ED%/}/usr/share/doc/${PF}/${__E_DOCDESTTREE#/}" ]]; then
			install -d "${ED%/}/usr/share/doc/${PF}/${__E_DOCDESTTREE#/}"
			local ret=$?
			if [[ ${ret} -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return ${ret}
			fi
		fi
	fi
}

insopts() {
	local IFS

	if has -s "$@"; then
		die "Never call insopts() with -s"
	else
		export INSOPTIONS=$*
	fi
}

diropts() {
	local IFS

	export DIROPTIONS=$*
}

exeopts() {
	local IFS

	if has -s "$@"; then
		die "Never call exeopts() with -s"
	else
		export EXEOPTIONS=$*
	fi
}

libopts() {
	local IFS

	if ! ___eapi_has_dolib_libopts; then
		die "'${FUNCNAME}' has been banned for EAPI '${EAPI}'"
	elif has -s "$@"; then
		die "Never call libopts() with -s"
	else
		export LIBOPTIONS=$*
	fi
}

docompress() {
	___eapi_has_docompress || die "'docompress' not supported in this EAPI"

	local f g
	if [[ ${1} = "-x" ]]; then
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
	local invert u=$1

	# If we got something like '!flag', then invert the return value
	if [[ ${u} == !* ]] ; then
		u=${u:1}
		invert=1
	fi

	if [[ ${EBUILD_PHASE} = depend ]] ; then
		# TODO: Add a registration interface for eclasses to register
		# any number of phase hooks, so that global scope eclass
		# initialization can by migrated to phase hooks in new EAPIs.
		# Example: add_phase_hook before pkg_setup ${ECLASS}_pre_pkg_setup
		#if [[ ${EAPI} && ${EAPI} != [0123] ]]; then
		#	die "use() called during invalid phase: ${EBUILD_PHASE}"
		#fi
		true

	# Make sure we have this USE flag in IUSE, but exempt binary
	# packages for API consumers like Entropy which do not require
	# a full profile with IUSE_IMPLICIT and stuff (see bug #456830).
	elif declare -F ___in_portage_iuse >/dev/null &&
		[[ -n ${EBUILD_PHASE} && -n ${PORTAGE_INTERNAL_CALLER} ]] ; then
		if ! ___in_portage_iuse "${u}"; then
			if [[ ${EMERGE_FROM} != binary &&
				! ${EAPI} =~ ^(0|1|2|3|4)$ ]] ; then
				# This is only strict starting with EAPI 5, since implicit IUSE
				# is not well defined for earlier EAPIs (see bug #449708).
				die "USE Flag '${u}' not in IUSE for ${CATEGORY}/${PF}"
			fi

			eqawarn "QA Notice: USE Flag '${u}' not" \
				"in IUSE for ${CATEGORY}/${PF}"
		fi
	fi

	contains_word "${u}" "${USE}"
	(( $? == invert ? 1 : 0 ))
}

use_with() {
	if [[ -z "${1}" ]]; then
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

	if use ${1}; then
		echo "--with-${UWORD}${UW_SUFFIX}"
	else
		echo "--without-${UWORD}"
	fi
	return 0
}

use_enable() {
	if [[ -z "${1}" ]]; then
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

	if use ${1}; then
		echo "--enable-${UWORD}${UE_SUFFIX}"
	else
		echo "--disable-${UWORD}"
	fi
	return 0
}

unpack() {
	local created_symlink
	local suffix_known
	local -a bzip2_cmd
	local basename
	local srcdir
	local suffix
	local f
	local -

	if (( $# == 0 )); then
		die "unpack: too few arguments (got 0; expected at least 1)"
	fi

	__unpack_tar() {
		local inner_suffix

		inner_suffix=${basename%.*} inner_suffix=${inner_suffix##*.}
		if ! ___eapi_unpack_is_case_sensitive; then
			inner_suffix=${inner_suffix,,}
		fi
		if [[ ${inner_suffix} == tar ]]; then
			"$@" -c -- "${srcdir}${f}" | tar xof -
		else
			"$@" -c -- "${srcdir}${f}" > "${basename%.*}"
		fi
	}

	__compose_bzip2_cmd() {
		local IFS

		read -rd '' -a bzip2_cmd <<<"${PORTAGE_BUNZIP2_COMMAND}"
		if (( ! ${#bzip2_cmd[@]} )); then
			read -rd '' -a bzip2_cmd <<<"${PORTAGE_BZIP2_COMMAND}"
			if (( ${#bzip2_cmd[@]} )); then
				bzip2_cmd+=( -d )
			else
				die "unpack: both PORTAGE_BUNZIP2_COMMAND and PORTAGE_BZIP2_COMMAND specify null commands"
			fi
		fi
	}

	shopt -o -s pipefail

	for f in "$@"; do
		basename=${f##*/}
		suffix=${basename##*.}

		# wrt PMS 12.3.15 Misc Commands
		if [[ ${f} != */* ]]; then
			# filename without path of any kind
			srcdir=${DISTDIR}/
		elif [[ ${f} == ./* ]]; then
			# relative path starting with './'
			srcdir=
		elif ___eapi_unpack_supports_absolute_paths; then
			# EAPI 6 allows absolute and deep relative paths
			srcdir=
			if [[ ${f} == "${DISTDIR%/}"/* ]]; then
				eqawarn "QA Notice: unpack called with redundant \${DISTDIR} in path"
			fi
		elif [[ ${f} == "${DISTDIR%/}"/* ]]; then
			die "Arguments to unpack() cannot begin with \${DISTDIR} in EAPI ${EAPI}"
		elif [[ ${f} == /* ]]; then
			die "Arguments to unpack() cannot be absolute in EAPI ${EAPI}"
		else
			die "Relative paths to unpack() must be prefixed with './' in EAPI ${EAPI}"
		fi

		# Tolerate only regular files that are non-empty.
		if [[ ! -f ${srcdir}${f} ]]; then
			die "unpack: ${f@Q} either does not exist or is not a regular file"
		elif [[ ! -s ${srcdir}${f} ]]; then
			die "unpack: ${f@Q} cannot be unpacked because it is an empty file"
		fi

		case ${suffix,,} in
			tar|tgz|tbz2|tbz|zip|jar|gz|z|bz2|bz|a|deb|lzma) ;;
			7z)      ___eapi_unpack_supports_7z  ;;
			rar)     ___eapi_unpack_supports_rar ;;
			lha|lzh) ___eapi_unpack_supports_lha ;;
			xz)      ___eapi_unpack_supports_xz  ;;
			txz)     ___eapi_unpack_supports_txz ;;
			*)       false                       ;;
		esac \
		&& suffix_known=1

		___eapi_unpack_is_case_sensitive \
		&& [[ ${suffix} != @("${suffix,,}"|ZIP|Z|7Z|RAR|LH[Aa]) ]] \
		&& suffix_known=0

		if (( suffix_known )); then
			__vecho ">>> Unpacking ${f@Q} to ${PWD}"
		else
			__vecho "=== Skipping unpack of ${f@Q}"
			continue
		fi

		case ${suffix,,} in
			tar)
				tar xof "${srcdir}${f}"
				;;
			tgz)
				tar xozf "${srcdir}${f}"
				;;
			tbz|tbz2)
				(( ${#bzip2_cmd[@]} )) || __compose_bzip2_cmd
				"${bzip2_cmd[@]}" -c -- "${srcdir}${f}" | tar xof -
				;;
			zip|jar)
				# unzip will interactively prompt under some error conditions,
				# as reported in bug #336285. Inducing EOF on STDIN makes for
				# an adequate countermeasure.
				unzip -qo "${srcdir}${f}" </dev/null
				;;
			gz|z)
				__unpack_tar gzip -d
				;;
			bz2|bz)
				(( ${#bzip2_cmd[@]} )) || __compose_bzip2_cmd
				__unpack_tar "${bzip2_cmd[@]}"
				;;
			7z)
				local my_output
				if ! my_output=$(7z x -y "${srcdir}${f}"); then
					printf '%s\n' "${my_output}" >&2
					false
				fi
				;;
			rar)
				unrar x -idq -o+ "${srcdir}${f}"
				;;
			lha|lzh)
				lha xfq "${srcdir}${f}"
				;;
			a)
				ar x "${srcdir}${f}"
				;;
			deb)
				# Unpacking .deb archives can not always be done with
				# `ar`.  For instance on AIX this doesn't work out.
				# If `ar` is not the GNU binutils version and we have
				# `deb2targz` installed, prefer it over `ar` for that
				# reason.  We just make sure on AIX `deb2targz` is
				# installed.
				if { hash deb2targz && ! ar --version | grep -q '^GNU ar'; } 2>/dev/null; then
					# deb2targz always extracts into the same directory as
					# the source file, so create a symlink in the current
					# working directory if necessary.
					if [[ ! "${srcdir}${f}" -ef "${basename}" ]]; then
						created_symlink=1
						ln -sf "${srcdir}${f}" "${basename}"
					fi \
					&& deb2targz "${basename}" \
					&& { (( ! created_symlink )) || rm -f "${basename}"; } \
					&& set -- "${basename%.deb}".tar.* \
					&& mv -f "$1" "data.tar.${1##*.}"
				else
					ar x "${srcdir}${f}"
				fi
				;;
			lzma)
				__unpack_tar lzma -d
				;;
			xz)
				__unpack_tar xz -T"$(___makeopts_jobs)" -d
				;;
			txz)
				XZ_OPT="-T$(___makeopts_jobs)" tar xof "${srcdir}${f}"
				;;
		esac || die "unpack: failure unpacking ${f@Q}"
	done

	# Do not chmod '.' since it's probably ${WORKDIR} and PORTAGE_WORKDIR_MODE
	# should be preserved.
	find . -mindepth 1 -maxdepth 1 ! -type l -exec "${PORTAGE_BIN_PATH}/chmod-lite" {} +
}

econf() {
	local x
	local pid=${BASHPID}

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

	local phase_func=$(__ebuild_arg_to_phase "${EBUILD_PHASE}")
	if [[ -n ${phase_func} ]] ; then
		if ! ___eapi_has_src_configure; then
			[[ ${phase_func} != src_compile ]] && \
				eqawarn "QA Notice: econf called in" \
					"${phase_func} instead of src_compile"
		else
			[[ ${phase_func} != src_configure ]] && \
				eqawarn "QA Notice: econf called in" \
					"${phase_func} instead of src_configure"
		fi
	fi

	: ${ECONF_SOURCE:=.}
	if [[ -x "${ECONF_SOURCE}/configure" ]]; then
		if [[ -n ${CONFIG_SHELL} && \
			"$(head -n1 "${ECONF_SOURCE}/configure")" =~ ^'#!'[[:space:]]*/bin/sh([[:space:]]|$) ]] ; then

			cp -p "${ECONF_SOURCE}/configure" "${ECONF_SOURCE}/configure._portage_tmp_.${pid}" || die
			sed -i \
				-e "1s:^#![[:space:]]*/bin/sh:#!${CONFIG_SHELL}:" \
				"${ECONF_SOURCE}/configure._portage_tmp_.${pid}" \
				|| die "Substition of shebang in '${ECONF_SOURCE}/configure' failed"

			# Preserve timestamp, see bug #440304
			touch -r "${ECONF_SOURCE}/configure" "${ECONF_SOURCE}/configure._portage_tmp_.${pid}" || die
			mv -f "${ECONF_SOURCE}/configure._portage_tmp_.${pid}" "${ECONF_SOURCE}/configure" || die
		fi

		if [[ -e "${EPREFIX}"/usr/share/gnuconfig/ ]]; then
			find "${WORKDIR}" -type f '(' \
			-name config.guess -o -name config.sub ')' -print0 | \
			while read -r -d $'\0' x ; do
				__vecho " * econf: updating ${x/${WORKDIR}\/} with ${EPREFIX}/usr/share/gnuconfig/${x##*/}"

				# Make sure we do this atomically incase we're run in parallel, bug #487478
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
				if [[ ${conf_help} == \
						*--disable-dependency-tracking[^A-Za-z0-9+_.-]* ]]; then
					conf_args+=( --disable-dependency-tracking )
				fi
			fi

			if ___eapi_econf_passes_--disable-silent-rules; then
				if [[ ${conf_help} == \
						*--disable-silent-rules[^A-Za-z0-9+_.-]* ]]; then
					conf_args+=( --disable-silent-rules )
				fi
			fi

			if ___eapi_econf_passes_--disable-static; then
				if [[ ${conf_help} == *--enable-shared[^A-Za-z0-9+_.-]* &&
						${conf_help} == *--enable-static[^A-Za-z0-9+_.-]* ]]; then
					conf_args+=( --disable-static )
				fi
			fi

			if ___eapi_econf_passes_--docdir_and_--htmldir; then
				if [[ ${conf_help} == *--docdir* ]]; then
					conf_args+=( --docdir="${EPREFIX}/usr/share/doc/${PF}" )
				fi

				if [[ ${conf_help} == *--htmldir* ]]; then
					conf_args+=( --htmldir="${EPREFIX}/usr/share/doc/${PF}/html" )
				fi
			fi

			if ___eapi_econf_passes_--with-sysroot; then
				if [[ ${conf_help} == *--with-sysroot[^A-Za-z0-9+_.-]* ]]; then
					conf_args+=( --with-sysroot="${ESYSROOT:-/}" )
				fi
			fi
		fi

		# If the profile defines a location to install libs to aside from default, pass it on.
		# If the ebuild passes in --libdir, they're responsible for the libdir fun.
		local libdir libdir_var="LIBDIR_${ABI}"
		if [[ -n ${ABI} && -n ${!libdir_var} ]] ; then
			libdir=${!libdir_var}
		fi

		if [[ -n ${libdir} ]] && ! __hasgq --libdir=\* "$@" ; then
			export CONF_PREFIX=$(__hasg --exec-prefix=\* "$@")
			[[ -z ${CONF_PREFIX} ]] && CONF_PREFIX=$(__hasg --prefix=\* "$@")

			: ${CONF_PREFIX:=${EPREFIX}/usr}
			CONF_PREFIX=${CONF_PREFIX#*=}

			[[ ${CONF_PREFIX} != /* ]] && CONF_PREFIX="/${CONF_PREFIX}"
			[[ ${libdir} != /* ]] && libdir="/${libdir}"

			conf_args+=(
				--libdir="$(__strip_duplicate_slashes "${CONF_PREFIX}${libdir}")"
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
			if [[ -s config.log ]]; then
				echo
				echo "!!! Please attach the following file when seeking support:"
				echo "!!! ${PWD}/config.log"
			fi

			# econf dies unconditionally in EAPIs 0 to 3
			___eapi_helpers_can_die || die "econf failed"
			__helpers_die "econf failed"
			return 1
		fi
	elif [[ -f "${ECONF_SOURCE}/configure" ]]; then
		die "configure is not executable"
	else
		die "no configure script found"
	fi
}

einstall() {
	if ! ___eapi_has_einstall; then
		die "'${FUNCNAME}' has been banned for EAPI '${EAPI}'"
		exit 1
	fi

	# CONF_PREFIX is only set if they didn't pass in libdir above.
	local LOCAL_EXTRA_EINSTALL="${EXTRA_EINSTALL}"
	if ! ___eapi_has_prefix_variables; then
		local ED=${D}
	fi

	local libdir libdir_var="LIBDIR_${ABI}"
	if [[ -n "${ABI}" && -n "${!libdir_var}" ]]; then
		libdir="${!libdir_var}"
	fi

	if [[ "${libdir}" && -v CONF_PREFIX ]]; then
		local destlibdir="${D%/}/${CONF_PREFIX}/${libdir}"
		destlibdir="$(__strip_duplicate_slashes "${destlibdir}")"
		LOCAL_EXTRA_EINSTALL="libdir=${destlibdir} ${LOCAL_EXTRA_EINSTALL}"
	fi

	if [[ -f Makefile || -f GNUmakefile || -f makefile ]] ; then
		if [[ "${PORTAGE_DEBUG}" == "1" ]]; then
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
	if [[ -x ./configure ]]; then
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

	if ${emake_cmd} ${internal_opts} check -n &> /dev/null; then
		__vecho "${emake_cmd} ${internal_opts} check" >&2
		${emake_cmd} ${internal_opts} check || \
			die "Make check failed. See above for details."
	elif ${emake_cmd} ${internal_opts} test -n &> /dev/null; then
		__vecho "${emake_cmd} ${internal_opts} test" >&2
		${emake_cmd} ${internal_opts} test || \
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
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]]; then
		emake || die "emake failed"
	fi
}

__eapi4_src_install() {
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]] ; then
		emake DESTDIR="${D}" install
	fi

	# To use declare -p determines whether a variable was declared but not
	# whether it was set. Unfortunately, the language of EAPI 4 requires
	# that it be this way.
	# https://projects.gentoo.org/pms/4/pms.html#x1-10400010.1.9
	if ! declare -p DOCS &>/dev/null ; then
		local d
		for d in README* ChangeLog AUTHORS NEWS TODO CHANGES \
				THANKS BUGS FAQ CREDITS CHANGELOG ; do
			[[ -s "${d}" ]] && dodoc "${d}"
		done
	elif [[ ${DOCS@a} == *a* ]] ; then
		dodoc "${DOCS[@]}"
	else
		dodoc ${DOCS}
	fi
}

__eapi6_src_prepare() {
	if [[ ${PATCHES@a} == *a* ]] ; then
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
	if [[ ${PATCHES@a} == *a* ]] ; then
		[[ ${#PATCHES[@]} -gt 0 ]] && eapply -- "${PATCHES[@]}"
	elif [[ -n ${PATCHES} ]]; then
		eapply -- ${PATCHES}
	fi

	eapply_user
}

___best_version_and_has_version_common() {
	local atom root root_arg

	# If ROOT is set to / below then SYSROOT cannot point elsewhere. Even if
	# ROOT is untouched, setting SYSROOT=/ for this command will always work.
	local -a cmd=(env SYSROOT=/)

	case $1 in
		--host-root|-r|-d|-b)
			root_arg=$1
			shift ;;
	esac
	atom=$1
	shift
	[[ $# -gt 0 ]] && die "${FUNCNAME[1]}: unused argument(s): $*"

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
				# with EPREFIX, ensure consistency here (bug #655414).
				root=/${PORTAGE_OVERRIDE_EPREFIX#/}
				cmd+=(EPREFIX="${PORTAGE_OVERRIDE_EPREFIX}")
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
						# Use /${PORTAGE_OVERRIDE_EPREFIX#/} to support older
						# EAPIs, as it is equivalent to BROOT.
						root=/${PORTAGE_OVERRIDE_EPREFIX#/}
						cmd+=(EPREFIX="${PORTAGE_OVERRIDE_EPREFIX}")
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

	if [[ -n ${PORTAGE_IPC_DAEMON} ]] ; then
		cmd+=("${PORTAGE_BIN_PATH}"/ebuild-ipc "${FUNCNAME[1]}" "${root}" "${atom}")
	else
		cmd+=("${PORTAGE_BIN_PATH}"/portageq-wrapper "${FUNCNAME[1]}" "${root}" "${atom}")
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

portageq() {
	die "portageq is not allowed in ebuild scope"
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
	einstalldocs() (
		local f

		if [[ ! -v DOCS ]]; then
			for f in README* ChangeLog AUTHORS NEWS TODO CHANGES \
				THANKS BUGS FAQ CREDITS CHANGELOG
			do
				if [[ -f ${f} && -s ${f} ]]; then
					docinto / && dodoc "${f}"
				fi
			done
		elif [[ ${DOCS@a} == *a* ]] && (( ${#DOCS[@]} )); then
			docinto / && dodoc -r "${DOCS[@]}"
		elif [[ ${DOCS@a} != *[aA]* && ${DOCS} ]]; then
			# shellcheck disable=2086
			docinto / && dodoc -r ${DOCS}
		fi

		if [[ ${HTML_DOCS@a} == *a* ]] && (( ${#HTML_DOCS[@]} )); then
			docinto html && dodoc -r "${HTML_DOCS[@]}"
		elif [[ ${HTML_DOCS@a} != *[aA]* && ${HTML_DOCS} ]]; then
			# shellcheck disable=2086
			docinto html && dodoc -r ${HTML_DOCS}
		fi
	)
fi

if ___eapi_has_eapply; then
	eapply() {
		local LC_ALL LC_COLLATE=C f i patch_cmd path
		local -a operands options

		_eapply_patch() {
			local prefix=$1 patch=$2 output IFS
			shift 2

			ebegin "${prefix:-Applying }${patch##*/}"
			# -p1 as a sane default
			# -f to avoid interactivity
			# -g0 to guarantee no VCS interaction
			# --no-backup-if-mismatch not to pollute the sources
			set -- -p1 -f -g0 --no-backup-if-mismatch "$@"
			if output=$(LC_ALL= LC_MESSAGES=C "${patch_cmd}" "$@" < "${patch}" 2>&1); then
				# The patch was successfully applied. Maintain
				# silence unless applied with fuzz.
				if [[ ${output} == *[0-9]' with fuzz '[0-9]* ]]; then
					printf '%s\n' "${output}"
				fi
				eend 0
			else
				printf '%s\n' "${output}" >&2
				eend 1
				__helpers_die "patch ${*@Q} failed with ${patch@Q}"
			fi
		}

		while (( $# )); do
			case $1 in
				--)
					shift
					operands+=("$@")
					break
					;;
				-*)
					if (( ! ${#operands[@]} )); then
						options+=("$1")
					else
						die "eapply: options must precede non-option arguments"
					fi
					;;
				*)
					operands+=("$1")
			esac
			shift
		done

		if (( ! ${#operands[@]} )); then
			die "eapply: no operands were specified"
		elif hash gpatch 2>/dev/null; then
			# for bsd userland support, use gpatch if available
			patch_cmd=gpatch
		else
			patch_cmd=patch
		fi

		for path in "${operands[@]}"; do
			if [[ -d ${path} ]]; then
				i=0
				for f in "${path}"/*; do
					if [[ ${f} == *.@(diff|patch) ]]; then
						if (( i++ == 0 )); then
							einfo "Applying patches from ${path} ..."
						fi
						_eapply_patch '  ' "${f}" "${options[@]}" || return
					fi
				done
				if (( i == 0 )); then
					die "No *.{patch,diff} files in directory ${path}"
				fi
			else
				_eapply_patch '' "${path}" "${options[@]}" || return
			fi
		done
	}
fi

if ___eapi_has_eapply_user; then
	eapply_user() {
		[[ ${EBUILD_PHASE} == prepare ]] || \
			die "eapply_user() called during invalid phase: ${EBUILD_PHASE}"

		# Keep path in __dyn_prepare in sync!
		local tagfile=${T}/.portage_user_patches_applied
		[[ -f ${tagfile} ]] && return
		>> "${tagfile}"

		local basedir=${PORTAGE_CONFIGROOT%/}/etc/portage/patches

		local columns=${COLUMNS:-0}
		[[ ${columns} == 0 ]] && columns=$(set -- $( ( stty size </dev/tty ) 2>/dev/null || echo 24 80 ) ; echo $2)
		(( columns > 0 )) || (( columns = 80 ))

		local -A patch_by
		local d f basename hr

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
		for d in "${basedir}"/"${CATEGORY}"/{"${PN}","${P}","${P}-${PR}"}{,":${SLOT%/*}"}; do
			for f in "${d}"/*; do
				if [[ ${f} == *.@(diff|patch) ]]; then
					basename=${f##*/}
					if [[ -s ${f} ]]; then
						patch_by[$basename]=${f}
					else
						unset -v 'patch_by[$basename]'
					fi
				fi
			done
		done

		if (( ${#patch_by[@]} > 0 )); then
			printf -v hr "%$(( columns - 3 ))s"
			hr=${hr//?/=}
			einfo "${PORTAGE_COLOR_INFO}${hr}${PORTAGE_COLOR_NORMAL}"
			einfo "Applying user patches from ${basedir} ..."
			while IFS= read -rd '' basename; do
				eapply -- "${patch_by[$basename]}"
			done < <(printf '%s\0' "${!patch_by[@]}" | LC_ALL=C sort -z)
			einfo "User patches applied."
			einfo "${PORTAGE_COLOR_INFO}${hr}${PORTAGE_COLOR_NORMAL}"
		fi
	}
fi

if ___eapi_has_in_iuse; then
	in_iuse() {
		if [[ ! $1 ]]; then
			printf >&2 '!!! %s\n' \
				"in_iuse() called without a parameter." \
				"in_iuse <USEFLAG>"
			die "in_iuse() called without a parameter"
		fi

		contains_word "$1" "${IUSE_EFFECTIVE}"
	}
fi
