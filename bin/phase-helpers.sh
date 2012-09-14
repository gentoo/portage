#!/bin/bash
# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

export DESTTREE=/usr
export INSDESTTREE=""
export _E_EXEDESTTREE_=""
export _E_DOCDESTTREE_=""
export INSOPTIONS="-m0644"
export EXEOPTIONS="-m0755"
export LIBOPTIONS="-m0644"
export DIROPTIONS="-m0755"
export MOPREFIX=${PN}
declare -a PORTAGE_DOCOMPRESS=( /usr/share/{doc,info,man} )
declare -a PORTAGE_DOCOMPRESS_SKIP=( /usr/share/doc/${PF}/html )

into() {
	if [ "$1" == "/" ]; then
		export DESTTREE=""
	else
		export DESTTREE=$1
		[[ " ${FEATURES} " == *" force-prefix "* ]] || \
			case "$EAPI" in 0|1|2) local ED=${D} ;; esac
		if [ ! -d "${ED}${DESTTREE}" ]; then
			install -d "${ED}${DESTTREE}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return $ret
			fi
		fi
	fi
}

insinto() {
	if [ "$1" == "/" ]; then
		export INSDESTTREE=""
	else
		export INSDESTTREE=$1
		[[ " ${FEATURES} " == *" force-prefix "* ]] || \
			case "$EAPI" in 0|1|2) local ED=${D} ;; esac
		if [ ! -d "${ED}${INSDESTTREE}" ]; then
			install -d "${ED}${INSDESTTREE}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				__helpers_die "${FUNCNAME[0]} failed"
				return $ret
			fi
		fi
	fi
}

exeinto() {
	if [ "$1" == "/" ]; then
		export _E_EXEDESTTREE_=""
	else
		export _E_EXEDESTTREE_="$1"
		[[ " ${FEATURES} " == *" force-prefix "* ]] || \
			case "$EAPI" in 0|1|2) local ED=${D} ;; esac
		if [ ! -d "${ED}${_E_EXEDESTTREE_}" ]; then
			install -d "${ED}${_E_EXEDESTTREE_}"
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
		[[ " ${FEATURES} " == *" force-prefix "* ]] || \
			case "$EAPI" in 0|1|2) local ED=${D} ;; esac
		if [ ! -d "${ED}usr/share/doc/${PF}/${_E_DOCDESTTREE_}" ]; then
			install -d "${ED}usr/share/doc/${PF}/${_E_DOCDESTTREE_}"
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
	export LIBOPTIONS="$@"

	# `install` should never be called with '-s' ...
	has -s ${LIBOPTIONS} && die "Never call libopts() with -s"
}

docompress() {
	has "${EAPI}" 0 1 2 3 && die "'docompress' not supported in this EAPI"

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

# adds ".keep" files so that dirs aren't auto-cleaned
keepdir() {
	dodir "$@"
	local x
	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local ED=${D} ;; esac
	if [ "$1" == "-R" ] || [ "$1" == "-r" ]; then
		shift
		find "$@" -type d -printf "${ED}%p/.keep_${CATEGORY}_${PN}-${SLOT}\n" \
			| tr "\n" "\0" | \
			while read -r -d $'\0' ; do
				>> "$REPLY" || \
					die "Failed to recursively create .keep files"
			done
	else
		for x in "$@"; do
			>> "${ED}${x}/.keep_${CATEGORY}_${PN}-${SLOT}" || \
				die "Failed to create .keep in ${ED}${x}"
		done
	fi
}


useq() {
	has $EBUILD_PHASE prerm postrm || eqawarn \
		"QA Notice: The 'useq' function is deprecated (replaced by 'use')"
	use ${1}
}

usev() {
	if use ${1}; then
		echo "${1#!}"
		return 0
	fi
	return 1
}

case "${EAPI}" in
	0|1|2|3|4|4-python|4-slot-abi) ;;
	*)
		usex() {
			if use "$1"; then
				echo "${2-yes}$4"
			else
				echo "${3-no}$5"
			fi
			return 0
		}
		;;
esac

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

	# Make sure we have this USE flag in IUSE
	elif [[ -n $PORTAGE_IUSE && -n $EBUILD_PHASE ]] ; then
		[[ $u =~ $PORTAGE_IUSE ]] || \
			eqawarn "QA Notice: USE Flag '${u}' not" \
				"in IUSE for ${CATEGORY}/${PF}"
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

	if ! has "${EAPI:-0}" 0 1 2 3 ; then
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

	if ! has "${EAPI:-0}" 0 1 2 3 ; then
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
	local y
	local myfail
	local eapi=${EAPI:-0}
	[ -z "$*" ] && die "Nothing passed to the 'unpack' command"

	for x in "$@"; do
		__vecho ">>> Unpacking ${x} to ${PWD}"
		y=${x%.*}
		y=${y##*.}

		if [[ ${x} == "./"* ]] ; then
			srcdir=""
		elif [[ ${x} == ${DISTDIR%/}/* ]] ; then
			die "Arguments to unpack() cannot begin with \${DISTDIR}."
		elif [[ ${x} == "/"* ]] ; then
			die "Arguments to unpack() cannot be absolute"
		else
			srcdir="${DISTDIR}/"
		fi
		[[ ! -s ${srcdir}${x} ]] && die "${x} does not exist"

		__unpack_tar() {
			if [ "${y}" == "tar" ]; then
				$1 -c -- "$srcdir$x" | tar xof -
				__assert_sigpipe_ok "$myfail"
			else
				local cwd_dest=${x##*/}
				cwd_dest=${cwd_dest%.*}
				$1 -c -- "${srcdir}${x}" > "${cwd_dest}" || die "$myfail"
			fi
		}

		myfail="failure unpacking ${x}"
		case "${x##*.}" in
			tar)
				tar xof "$srcdir$x" || die "$myfail"
				;;
			tgz)
				tar xozf "$srcdir$x" || die "$myfail"
				;;
			tbz|tbz2)
				${PORTAGE_BUNZIP2_COMMAND:-${PORTAGE_BZIP2_COMMAND} -d} -c -- "$srcdir$x" | tar xof -
				__assert_sigpipe_ok "$myfail"
				;;
			ZIP|zip|jar)
				# unzip will interactively prompt under some error conditions,
				# as reported in bug #336285
				( set +x ; while true ; do echo n || break ; done ) | \
				unzip -qo "${srcdir}${x}" || die "$myfail"
				;;
			gz|Z|z)
				__unpack_tar "gzip -d"
				;;
			bz2|bz)
				__unpack_tar "${PORTAGE_BUNZIP2_COMMAND:-${PORTAGE_BZIP2_COMMAND} -d}"
				;;
			7Z|7z)
				local my_output
				my_output="$(7z x -y "${srcdir}${x}")"
				if [ $? -ne 0 ]; then
					echo "${my_output}" >&2
					die "$myfail"
				fi
				;;
			RAR|rar)
				unrar x -idq -o+ "${srcdir}${x}" || die "$myfail"
				;;
			LHa|LHA|lha|lzh)
				lha xfq "${srcdir}${x}" || die "$myfail"
				;;
			a)
				ar x "${srcdir}${x}" || die "$myfail"
				;;
			deb)
				# Unpacking .deb archives can not always be done with
				# `ar`.  For instance on AIX this doesn't work out.  If
				# we have `deb2targz` installed, prefer it over `ar` for
				# that reason.  We just make sure on AIX `deb2targz` is
				# installed.
				if type -P deb2targz > /dev/null; then
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
					mv -f "${y%.deb}".tar.gz data.tar.gz || die "$myfail"
				else
					ar x "$srcdir$x" || die "$myfail"
				fi
				;;
			lzma)
				__unpack_tar "lzma -d"
				;;
			xz)
				if has $eapi 0 1 2 ; then
					__vecho "unpack ${x}: file format not recognized. Ignoring."
				else
					__unpack_tar "xz -d"
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
		${XARGS} -0 chmod -fR a+rX,u+w,g-w,o-w
}

econf() {
	local x

	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local EPREFIX= ;; esac

	__hasg() {
		local x s=$1
		shift
		for x ; do [[ ${x} == ${s} ]] && echo "${x}" && return 0 ; done
		return 1
	}

	__hasgq() { __hasg "$@" >/dev/null ; }

	local phase_func=$(__ebuild_arg_to_phase "$EAPI" "$EBUILD_PHASE")
	if [[ -n $phase_func ]] ; then
		if has "$EAPI" 0 1 ; then
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
			sed -e "1s:^#![[:space:]]*/bin/sh:#!$CONFIG_SHELL:" -i "$ECONF_SOURCE/configure" || \
				die "Substition of shebang in '$ECONF_SOURCE/configure' failed"
		fi
		if [ -e "${EPREFIX}"/usr/share/gnuconfig/ ]; then
			find "${WORKDIR}" -type f '(' \
			-name config.guess -o -name config.sub ')' -print0 | \
			while read -r -d $'\0' x ; do
				__vecho " * econf: updating ${x/${WORKDIR}\/} with ${EPREFIX}/usr/share/gnuconfig/${x##*/}"
				cp -f "${EPREFIX}"/usr/share/gnuconfig/"${x##*/}" "${x}"
			done
		fi

		# EAPI=4 adds --disable-dependency-tracking to econf
		case "${EAPI}" in
			0|1|2|3)
				;;
			*)
				local conf_help=$("${ECONF_SOURCE}/configure" --help 2>/dev/null)
				case "${conf_help}" in
					*--disable-dependency-tracking*)
						set -- --disable-dependency-tracking "$@"
						;;
				esac
				case "${EAPI}" in
					4|4-python|4-slot-abi)
						;;
					*)
						case "${conf_help}" in
							*--disable-silent-rules*)
								set -- --disable-silent-rules "$@"
								;;
						esac
						;;
				esac
				;;
		esac

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
			set -- --libdir="$(__strip_duplicate_slashes ${CONF_PREFIX}${CONF_LIBDIR})" "$@"
		fi

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
			"$@" \
			${EXTRA_ECONF}
		__vecho "${ECONF_SOURCE}/configure" "$@"

		if ! "${ECONF_SOURCE}/configure" "$@" ; then

			if [ -s config.log ]; then
				echo
				echo "!!! Please attach the following file when seeking support:"
				echo "!!! ${PWD}/config.log"
			fi
			die "econf failed"
		fi
	elif [ -f "${ECONF_SOURCE}/configure" ]; then
		die "configure is not executable"
	else
		die "no configure script found"
	fi
}

einstall() {
	# CONF_PREFIX is only set if they didn't pass in libdir above.
	local LOCAL_EXTRA_EINSTALL="${EXTRA_EINSTALL}"
	[[ " ${FEATURES} " == *" force-prefix "* ]] || \
		case "$EAPI" in 0|1|2) local ED=${D} ;; esac
	LIBDIR_VAR="LIBDIR_${ABI}"
	if [ -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
		CONF_LIBDIR="${!LIBDIR_VAR}"
	fi
	unset LIBDIR_VAR
	if [ -n "${CONF_LIBDIR}" ] && [ "${CONF_PREFIX:+set}" = set ]; then
		EI_DESTLIBDIR="${D}/${CONF_PREFIX}/${CONF_LIBDIR}"
		EI_DESTLIBDIR="$(__strip_duplicate_slashes ${EI_DESTLIBDIR})"
		LOCAL_EXTRA_EINSTALL="libdir=${EI_DESTLIBDIR} ${LOCAL_EXTRA_EINSTALL}"
		unset EI_DESTLIBDIR
	fi

	if [ -f ./[mM]akefile -o -f ./GNUmakefile ] ; then
		if [ "${PORTAGE_DEBUG}" == "1" ]; then
			${MAKE:-make} -n prefix="${ED}usr" \
				datadir="${ED}usr/share" \
				infodir="${ED}usr/share/info" \
				localstatedir="${ED}var/lib" \
				mandir="${ED}usr/share/man" \
				sysconfdir="${ED}etc" \
				${LOCAL_EXTRA_EINSTALL} \
				${MAKEOPTS} ${EXTRA_EMAKE} -j1 \
				"$@" install
		fi
		${MAKE:-make} prefix="${ED}usr" \
			datadir="${ED}usr/share" \
			infodir="${ED}usr/share/info" \
			localstatedir="${ED}var/lib" \
			mandir="${ED}usr/share/man" \
			sysconfdir="${ED}etc" \
			${LOCAL_EXTRA_EINSTALL} \
			${MAKEOPTS} ${EXTRA_EMAKE} -j1 \
			"$@" install || die "einstall failed"
	else
		die "no Makefile found"
	fi
}

__eapi0_pkg_nofetch() {
	[ -z "${SRC_URI}" ] && return

	elog "The following are listed in SRC_URI for ${PN}:"
	local x
	for x in $(echo ${SRC_URI}); do
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
	case "$EAPI" in
		0|1|2|3|4|4-python|4-slot-abi)
			internal_opts+=" -j1"
			;;
	esac
	if $emake_cmd ${internal_opts} check -n &> /dev/null; then
		__vecho ">>> Test phase [check]: ${CATEGORY}/${PF}"
		$emake_cmd ${internal_opts} check || \
			die "Make check failed. See above for details."
	elif $emake_cmd ${internal_opts} test -n &> /dev/null; then
		__vecho ">>> Test phase [test]: ${CATEGORY}/${PF}"
		$emake_cmd ${internal_opts} test || \
			die "Make test failed. See above for details."
	else
		__vecho ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
}

__eapi1_src_compile() {
	__eapi2_src_configure
	__eapi2_src_compile
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
	elif [[ $(declare -p DOCS) == "declare -a "* ]] ; then
		dodoc "${DOCS[@]}"
	else
		dodoc ${DOCS}
	fi
}

# @FUNCTION: has_version
# @USAGE: [--host-root] <DEPEND ATOM>
# @DESCRIPTION:
# Return true if given package is installed. Otherwise return false.
# Callers may override the ROOT variable in order to match packages from an
# alternative ROOT.
has_version() {

	local atom eroot host_root=false root=${ROOT}
	if [[ $1 == --host-root ]] ; then
		host_root=true
		shift
	fi
	atom=$1
	shift
	[ $# -gt 0 ] && die "${FUNCNAME[0]}: unused argument(s): $*"

	if ${host_root} ; then
		case "${EAPI}" in
			0|1|2|3|4|4-python|4-slot-abi)
				die "${FUNCNAME[0]}: option --host-root is not supported with EAPI ${EAPI}"
				;;
		esac
		root=/
	fi

	case "$EAPI" in
		0|1|2)
			[[ " ${FEATURES} " == *" force-prefix "* ]] && \
				eroot=${root%/}${EPREFIX}/ || eroot=${root}
			;;
		*)
			eroot=${root%/}${EPREFIX}/
			;;
	esac
	if [[ -n $PORTAGE_IPC_DAEMON ]] ; then
		"$PORTAGE_BIN_PATH"/ebuild-ipc has_version "${eroot}" "${atom}"
	else
		PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
		"${PORTAGE_PYTHON:-/usr/bin/python}" "${PORTAGE_BIN_PATH}/portageq" has_version "${eroot}" "${atom}"
	fi
	local retval=$?
	case "${retval}" in
		0|1)
			return ${retval}
			;;
		*)
			die "unexpected portageq exit code: ${retval}"
			;;
	esac
}

# @FUNCTION: best_version
# @USAGE: [--host-root] <DEPEND ATOM>
# @DESCRIPTION:
# Returns the best/most-current match.
# Callers may override the ROOT variable in order to match packages from an
# alternative ROOT.
best_version() {

	local atom eroot host_root=false root=${ROOT}
	if [[ $1 == --host-root ]] ; then
		host_root=true
		shift
	fi
	atom=$1
	shift
	[ $# -gt 0 ] && die "${FUNCNAME[0]}: unused argument(s): $*"

	if ${host_root} ; then
		case "${EAPI}" in
			0|1|2|3|4|4-python|4-slot-abi)
				die "${FUNCNAME[0]}: option --host-root is not supported with EAPI ${EAPI}"
				;;
		esac
		root=/
	fi

	case "$EAPI" in
		0|1|2)
			[[ " ${FEATURES} " == *" force-prefix "* ]] && \
				eroot=${root%/}${EPREFIX}/ || eroot=${root}
			;;
		*)
			eroot=${root%/}${EPREFIX}/
			;;
	esac
	if [[ -n $PORTAGE_IPC_DAEMON ]] ; then
		"$PORTAGE_BIN_PATH"/ebuild-ipc best_version "${eroot}" "${atom}"
	else
		PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
		"${PORTAGE_PYTHON:-/usr/bin/python}" "${PORTAGE_BIN_PATH}/portageq" best_version "${eroot}" "${atom}"
	fi
	local retval=$?
	case "${retval}" in
		0|1)
			return ${retval}
			;;
		*)
			die "unexpected portageq exit code: ${retval}"
			;;
	esac
}
