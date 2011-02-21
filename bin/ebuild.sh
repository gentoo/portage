#!/bin/bash
# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

PORTAGE_BIN_PATH="${PORTAGE_BIN_PATH:-/usr/lib/portage/bin}"
PORTAGE_PYM_PATH="${PORTAGE_PYM_PATH:-/usr/lib/portage/pym}"

if [[ $PORTAGE_SANDBOX_COMPAT_LEVEL -lt 22 ]] ; then
	# Ensure that /dev/std* streams have appropriate sandbox permission for
	# bug #288863. This can be removed after sandbox is fixed and portage
	# depends on the fixed version (sandbox-2.2 has the fix but it is
	# currently unstable).
	export SANDBOX_WRITE="${SANDBOX_WRITE:+${SANDBOX_WRITE}:}/dev/stdout:/dev/stderr"
	export SANDBOX_READ="${SANDBOX_READ:+${SANDBOX_READ}:}/dev/stdin"
fi

# Don't use sandbox's BASH_ENV for new shells because it does
# 'source /etc/profile' which can interfere with the build
# environment by modifying our PATH.
unset BASH_ENV

ROOTPATH=${ROOTPATH##:}
ROOTPATH=${ROOTPATH%%:}
PREROOTPATH=${PREROOTPATH##:}
PREROOTPATH=${PREROOTPATH%%:}
PATH=$PORTAGE_BIN_PATH/ebuild-helpers:$PREROOTPATH${PREROOTPATH:+:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin${ROOTPATH:+:}$ROOTPATH
export PATH

# This is just a temporary workaround for portage-9999 users since
# earlier portage versions do not detect a version change in this case
# (9999 to 9999) and therefore they try execute an incompatible version of
# ebuild.sh during the upgrade.
export PORTAGE_BZIP2_COMMAND=${PORTAGE_BZIP2_COMMAND:-bzip2} 

# These two functions wrap sourcing and calling respectively.  At present they
# perform a qa check to make sure eclasses and ebuilds and profiles don't mess
# with shell opts (shopts).  Ebuilds/eclasses changing shopts should reset them 
# when they are done.

qa_source() {
	local shopts=$(shopt) OLDIFS="$IFS"
	local retval
	source "$@"
	retval=$?
	set +e
	[[ $shopts != $(shopt) ]] &&
		eqawarn "QA Notice: Global shell options changed and were not restored while sourcing '$*'"
	[[ "$IFS" != "$OLDIFS" ]] &&
		eqawarn "QA Notice: Global IFS changed and was not restored while sourcing '$*'"
	return $retval
}

qa_call() {
	local shopts=$(shopt) OLDIFS="$IFS"
	local retval
	"$@"
	retval=$?
	set +e
	[[ $shopts != $(shopt) ]] &&
		eqawarn "QA Notice: Global shell options changed and were not restored while calling '$*'"
	[[ "$IFS" != "$OLDIFS" ]] &&
		eqawarn "QA Notice: Global IFS changed and was not restored while calling '$*'"
	return $retval
}

EBUILD_SH_ARGS="$*"

shift $#

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# Unset some variables that break things.
unset GZIP BZIP BZIP2 CDPATH GREP_OPTIONS GREP_COLOR GLOBIGNORE

source "${PORTAGE_BIN_PATH}/isolated-functions.sh"  &>/dev/null

[[ $PORTAGE_QUIET != "" ]] && export PORTAGE_QUIET

# sandbox support functions; defined prior to profile.bashrc srcing, since the profile might need to add a default exception (/usr/lib64/conftest fex)
_sb_append_var() {
	local _v=$1 ; shift
	local var="SANDBOX_${_v}"
	[[ -z $1 || -n $2 ]] && die "Usage: add$(echo ${_v} | \
		LC_ALL=C tr [:upper:] [:lower:]) <colon-delimited list of paths>"
	export ${var}="${!var:+${!var}:}$1"
}
# bash-4 version:
# local var="SANDBOX_${1^^}"
# addread() { _sb_append_var ${0#add} "$@" ; }
addread()    { _sb_append_var READ    "$@" ; }
addwrite()   { _sb_append_var WRITE   "$@" ; }
adddeny()    { _sb_append_var DENY    "$@" ; }
addpredict() { _sb_append_var PREDICT "$@" ; }

addwrite "${PORTAGE_TMPDIR}"
addread "/:${PORTAGE_TMPDIR}"
[[ -n ${PORTAGE_GPG_DIR} ]] && addpredict "${PORTAGE_GPG_DIR}"

# Avoid sandbox violations in temporary directories.
if [[ -w $T ]] ; then
	export TEMP=$T
	export TMP=$T
	export TMPDIR=$T
elif [[ $SANDBOX_ON = 1 ]] ; then
	for x in TEMP TMP TMPDIR ; do
		[[ -n ${!x} ]] && addwrite "${!x}"
	done
	unset x
fi

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON=0

lchown() {
	chown -h "$@"
}

lchgrp() {
	chgrp -h "$@"
}

esyslog() {
	# Custom version of esyslog() to take care of the "Red Star" bug.
	# MUST follow functions.sh to override the "" parameter problem.
	return 0
}

use() {
	useq ${1}
}

usev() {
	if useq ${1}; then
		echo "${1#!}"
		return 0
	fi
	return 1
}

useq() {
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
		#if [[ -n $EAPI ]] && ! hasq "$EAPI" 0 1 2 3 ; then
		#	die "use() called during invalid phase: $EBUILD_PHASE"
		#fi
		true

	# Make sure we have this USE flag in IUSE
	elif [[ -n $PORTAGE_IUSE && -n $EBUILD_PHASE ]] ; then
		[[ $u =~ $PORTAGE_IUSE ]] || \
			eqawarn "QA Notice: USE Flag '${u}' not" \
				"in IUSE for ${CATEGORY}/${PF}"
	fi

	if hasq ${u} ${USE} ; then
		return ${found}
	else
		return $((!found))
	fi
}

# Return true if given package is installed. Otherwise return false.
# Takes single depend-type atoms.
has_version() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls (has_version calls portageq) are not allowed in the global scope"
	fi

	if [[ -n $PORTAGE_IPC_DAEMON ]] ; then
		"$PORTAGE_BIN_PATH"/ebuild-ipc has_version "$ROOT" "$1"
	else
		PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
		"${PORTAGE_PYTHON:-/usr/bin/python}" "${PORTAGE_BIN_PATH}/portageq" has_version "${ROOT}" "$1"
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

portageq() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls are not allowed in the global scope"
	fi

	PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
	"${PORTAGE_PYTHON:-/usr/bin/python}" "${PORTAGE_BIN_PATH}/portageq" "$@"
}


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------


# Returns the best/most-current match.
# Takes single depend-type atoms.
best_version() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls (best_version calls portageq) are not allowed in the global scope"
	fi

	if [[ -n $PORTAGE_IPC_DAEMON ]] ; then
		"$PORTAGE_BIN_PATH"/ebuild-ipc best_version "$ROOT" "$1"
	else
		PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
		"${PORTAGE_PYTHON:-/usr/bin/python}" "${PORTAGE_BIN_PATH}/portageq" 'best_version' "${ROOT}" "$1"
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

	if useq $1; then
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

	if useq $1; then
		echo "--enable-${UWORD}${UE_SUFFIX}"
	else
		echo "--disable-${UWORD}"
	fi
	return 0
}

register_die_hook() {
	local x
	for x in $* ; do
		hasq $x $EBUILD_DEATH_HOOKS || \
			export EBUILD_DEATH_HOOKS="$EBUILD_DEATH_HOOKS $x"
	done
}

register_success_hook() {
	local x
	for x in $* ; do
		hasq $x $EBUILD_SUCCESS_HOOKS || \
			export EBUILD_SUCCESS_HOOKS="$EBUILD_SUCCESS_HOOKS $x"
	done
}

# Ensure that $PWD is sane whenever possible, to protect against
# exploitation of insecure search path for python -c in ebuilds.
# See bug #239560.
if ! hasq "$EBUILD_PHASE" clean cleanrm depend help ; then
	cd "$PORTAGE_BUILDDIR" || \
		die "PORTAGE_BUILDDIR does not exist: '$PORTAGE_BUILDDIR'"
fi

#if no perms are specified, dirs/files will have decent defaults
#(not secretive, but not stupid)
umask 022
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

# adds ".keep" files so that dirs aren't auto-cleaned
keepdir() {
	dodir "$@"
	local x
	if [ "$1" == "-R" ] || [ "$1" == "-r" ]; then
		shift
		find "$@" -type d -printf "${D}%p/.keep_${CATEGORY}_${PN}-${SLOT}\n" \
			| tr "\n" "\0" | \
			while read -r -d $'\0' ; do
				>> "$REPLY" || \
					die "Failed to recursively create .keep files"
			done
	else
		for x in "$@"; do
			>> "${D}${x}/.keep_${CATEGORY}_${PN}-${SLOT}" || \
				die "Failed to create .keep in ${D}${x}"
		done
	fi
}

unpack() {
	local srcdir
	local x
	local y
	local myfail
	local eapi=${EAPI:-0}
	[ -z "$*" ] && die "Nothing passed to the 'unpack' command"

	for x in "$@"; do
		vecho ">>> Unpacking ${x} to ${PWD}"
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

		_unpack_tar() {
			if [ "${y}" == "tar" ]; then
				$1 -c -- "$srcdir$x" | tar xof -
				assert_sigpipe_ok "$myfail"
			else
				$1 -c -- "${srcdir}${x}" > ${x%.*} || die "$myfail"
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
				assert_sigpipe_ok "$myfail"
				;;
			ZIP|zip|jar)
				# unzip will interactively prompt under some error conditions,
				# as reported in bug #336285
				( while true ; do echo n || break ; done ) | \
				unzip -qo "${srcdir}${x}" || die "$myfail"
				;;
			gz|Z|z)
				_unpack_tar "gzip -d"
				;;
			bz2|bz)
				_unpack_tar "${PORTAGE_BUNZIP2_COMMAND:-${PORTAGE_BZIP2_COMMAND} -d}"
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
				_unpack_tar "lzma -d"
				;;
			xz)
				if hasq $eapi 0 1 2 ; then
					vecho "unpack ${x}: file format not recognized. Ignoring."
				else
					_unpack_tar "xz -d"
				fi
				;;
			*)
				vecho "unpack ${x}: file format not recognized. Ignoring."
				;;
		esac
	done
	# Do not chmod '.' since it's probably ${WORKDIR} and PORTAGE_WORKDIR_MODE
	# should be preserved.
	find . -mindepth 1 -maxdepth 1 ! -type l -print0 | \
		${XARGS} -0 chmod -fR a+rX,u+w,g-w,o-w
}

strip_duplicate_slashes() {
	if [[ -n $1 ]] ; then
		local removed=$1
		while [[ ${removed} == *//* ]] ; do
			removed=${removed//\/\///}
		done
		echo ${removed}
	fi
}

hasg() {
    local x s=$1
    shift
    for x ; do [[ ${x} == ${s} ]] && echo "${x}" && return 0 ; done
    return 1
}
hasgq() { hasg "$@" >/dev/null ; }
econf() {
	local x

	local phase_func=$(_ebuild_arg_to_phase "$EAPI" "$EBUILD_PHASE")
	if [[ -n $phase_func ]] ; then
		if hasq "$EAPI" 0 1 ; then
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
		if [ -e /usr/share/gnuconfig/ ]; then
			find "${WORKDIR}" -type f '(' \
			-name config.guess -o -name config.sub ')' -print0 | \
			while read -r -d $'\0' x ; do
				vecho " * econf: updating ${x/${WORKDIR}\/} with /usr/share/gnuconfig/${x##*/}"
				cp -f /usr/share/gnuconfig/"${x##*/}" "${x}"
			done
		fi

		# EAPI=4 adds --disable-dependency-tracking to econf
		if ! hasq "$EAPI" 0 1 2 3 3_pre2 && \
			"${ECONF_SOURCE}/configure" --help 2>/dev/null | \
			grep -q disable-dependency-tracking ; then
			set -- --disable-dependency-tracking "$@"
		fi

		# if the profile defines a location to install libs to aside from default, pass it on.
		# if the ebuild passes in --libdir, they're responsible for the conf_libdir fun.
		local CONF_LIBDIR LIBDIR_VAR="LIBDIR_${ABI}"
		if [[ -n ${ABI} && -n ${!LIBDIR_VAR} ]] ; then
			CONF_LIBDIR=${!LIBDIR_VAR}
		fi
		if [[ -n ${CONF_LIBDIR} ]] && ! hasgq --libdir=\* "$@" ; then
			export CONF_PREFIX=$(hasg --exec-prefix=\* "$@")
			[[ -z ${CONF_PREFIX} ]] && CONF_PREFIX=$(hasg --prefix=\* "$@")
			: ${CONF_PREFIX:=/usr}
			CONF_PREFIX=${CONF_PREFIX#*=}
			[[ ${CONF_PREFIX} != /* ]] && CONF_PREFIX="/${CONF_PREFIX}"
			[[ ${CONF_LIBDIR} != /* ]] && CONF_LIBDIR="/${CONF_LIBDIR}"
			set -- --libdir="$(strip_duplicate_slashes ${CONF_PREFIX}${CONF_LIBDIR})" "$@"
		fi

		set -- \
			--prefix=/usr \
			${CBUILD:+--build=${CBUILD}} \
			--host=${CHOST} \
			${CTARGET:+--target=${CTARGET}} \
			--mandir=/usr/share/man \
			--infodir=/usr/share/info \
			--datadir=/usr/share \
			--sysconfdir=/etc \
			--localstatedir=/var/lib \
			"$@" \
			${EXTRA_ECONF}
		vecho "${ECONF_SOURCE}/configure" "$@"

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
	LIBDIR_VAR="LIBDIR_${ABI}"
	if [ -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
		CONF_LIBDIR="${!LIBDIR_VAR}"
	fi
	unset LIBDIR_VAR
	if [ -n "${CONF_LIBDIR}" ] && [ "${CONF_PREFIX:+set}" = set ]; then
		EI_DESTLIBDIR="${D}/${CONF_PREFIX}/${CONF_LIBDIR}"
		EI_DESTLIBDIR="$(strip_duplicate_slashes ${EI_DESTLIBDIR})"
		LOCAL_EXTRA_EINSTALL="libdir=${EI_DESTLIBDIR} ${LOCAL_EXTRA_EINSTALL}"
		unset EI_DESTLIBDIR
	fi

	if [ -f ./[mM]akefile -o -f ./GNUmakefile ] ; then
		if [ "${PORTAGE_DEBUG}" == "1" ]; then
			${MAKE:-make} -n prefix="${D}usr" \
				datadir="${D}usr/share" \
				infodir="${D}usr/share/info" \
				localstatedir="${D}var/lib" \
				mandir="${D}usr/share/man" \
				sysconfdir="${D}etc" \
				${LOCAL_EXTRA_EINSTALL} \
				${MAKEOPTS} ${EXTRA_EMAKE} -j1 \
				"$@" install
		fi
		${MAKE:-make} prefix="${D}usr" \
			datadir="${D}usr/share" \
			infodir="${D}usr/share/info" \
			localstatedir="${D}var/lib" \
			mandir="${D}usr/share/man" \
			sysconfdir="${D}etc" \
			${LOCAL_EXTRA_EINSTALL} \
			${MAKEOPTS} ${EXTRA_EMAKE} -j1 \
			"$@" install || die "einstall failed"
	else
		die "no Makefile found"
	fi
}

_eapi0_pkg_nofetch() {
	[ -z "${SRC_URI}" ] && return

	elog "The following are listed in SRC_URI for ${PN}:"
	local x
	for x in $(echo ${SRC_URI}); do
		elog "   ${x}"
	done
}

_eapi0_src_unpack() {
	[[ -n ${A} ]] && unpack ${A}
}

_eapi0_src_compile() {
	if [ -x ./configure ] ; then
		econf
	fi
	_eapi2_src_compile
}

_eapi0_src_test() {
	# Since we don't want emake's automatic die
	# support (EAPI 4 and later), and we also don't
	# want the warning messages that it produces if
	# we call it in 'nonfatal' mode, we use emake_cmd
	# to emulate the desired parts of emake behavior.
	local emake_cmd="${MAKE:-make} ${MAKEOPTS} ${EXTRA_EMAKE}"
	if $emake_cmd -j1 check -n &> /dev/null; then
		vecho ">>> Test phase [check]: ${CATEGORY}/${PF}"
		if ! $emake_cmd -j1 check; then
			hasq test $FEATURES && die "Make check failed. See above for details."
			hasq test $FEATURES || eerror "Make check failed. See above for details."
		fi
	elif $emake_cmd -j1 test -n &> /dev/null; then
		vecho ">>> Test phase [test]: ${CATEGORY}/${PF}"
		if ! $emake_cmd -j1 test; then
			hasq test $FEATURES && die "Make test failed. See above for details."
			hasq test $FEATURES || eerror "Make test failed. See above for details."
		fi
	else
		vecho ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
}

_eapi1_src_compile() {
	_eapi2_src_configure
	_eapi2_src_compile
}

_eapi2_src_configure() {
	if [[ -x ${ECONF_SOURCE:-.}/configure ]] ; then
		econf
	fi
}

_eapi2_src_compile() {
	if [ -f Makefile ] || [ -f GNUmakefile ] || [ -f makefile ]; then
		emake || die "emake failed"
	fi
}

_eapi4_src_install() {
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

ebuild_phase() {
	declare -F "$1" >/dev/null && qa_call $1
}

ebuild_phase_with_hooks() {
	local x phase_name=${1}
	for x in {pre_,,post_}${phase_name} ; do
		ebuild_phase ${x}
	done
}

dyn_pretend() {
	if [[ -e $PORTAGE_BUILDDIR/.pretended ]] ; then
		vecho ">>> It appears that '$PF' is already pretended; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.pretended' to force pretend."
		return 0
	fi
	ebuild_phase pre_pkg_pretend
	ebuild_phase pkg_pretend
	>> "$PORTAGE_BUILDDIR/.pretended" || \
		die "Failed to create $PORTAGE_BUILDDIR/.pretended"
	ebuild_phase post_pkg_pretend
}

dyn_setup() {
	if [[ -e $PORTAGE_BUILDDIR/.setuped ]] ; then
		vecho ">>> It appears that '$PF' is already setup; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.setuped' to force setup."
		return 0
	fi
	ebuild_phase pre_pkg_setup
	ebuild_phase pkg_setup
	>> "$PORTAGE_BUILDDIR/.setuped" || \
		die "Failed to create $PORTAGE_BUILDDIR/.setuped"
	ebuild_phase post_pkg_setup
}

dyn_unpack() {
	local newstuff="no"
	if [ -e "${WORKDIR}" ]; then
		local x
		local checkme
		for x in $A ; do
			vecho ">>> Checking ${x}'s mtime..."
			if [ "${PORTAGE_ACTUAL_DISTDIR:-${DISTDIR}}/${x}" -nt "${WORKDIR}" ]; then
				vecho ">>> ${x} has been updated; recreating WORKDIR..."
				newstuff="yes"
				break
			fi
		done
		if [ ! -f "${PORTAGE_BUILDDIR}/.unpacked" ] ; then
			vecho ">>> Not marked as unpacked; recreating WORKDIR..."
			newstuff="yes"
		fi
	fi
	if [ "${newstuff}" == "yes" ]; then
		# We don't necessarily have privileges to do a full dyn_clean here.
		rm -rf "${PORTAGE_BUILDDIR}"/{.setuped,.unpacked,.prepared,.configured,.compiled,.tested,.installed,.packaged,build-info}
		if ! hasq keepwork $FEATURES ; then
			rm -rf "${WORKDIR}"
		fi
		if [ -d "${T}" ] && \
			! hasq keeptemp $FEATURES ; then
			rm -rf "${T}" && mkdir "${T}"
		fi
	fi
	if [ -e "${WORKDIR}" ]; then
		if [ "$newstuff" == "no" ]; then
			vecho ">>> WORKDIR is up-to-date, keeping..."
			return 0
		fi
	fi

	if [ ! -d "${WORKDIR}" ]; then
		install -m${PORTAGE_WORKDIR_MODE:-0700} -d "${WORKDIR}" || die "Failed to create dir '${WORKDIR}'"
	fi
	cd "${WORKDIR}" || die "Directory change failed: \`cd '${WORKDIR}'\`"
	ebuild_phase pre_src_unpack
	vecho ">>> Unpacking source..."
	ebuild_phase src_unpack
	>> "$PORTAGE_BUILDDIR/.unpacked" || \
		die "Failed to create $PORTAGE_BUILDDIR/.unpacked"
	vecho ">>> Source unpacked in ${WORKDIR}"
	ebuild_phase post_src_unpack
}

dyn_clean() {
	if [ -z "${PORTAGE_BUILDDIR}" ]; then
		echo "Aborting clean phase because PORTAGE_BUILDDIR is unset!"
		return 1
	elif [ ! -d "${PORTAGE_BUILDDIR}" ] ; then
		return 0
	fi
	if hasq chflags $FEATURES ; then
		chflags -R noschg,nouchg,nosappnd,nouappnd "${PORTAGE_BUILDDIR}"
		chflags -R nosunlnk,nouunlnk "${PORTAGE_BUILDDIR}" 2>/dev/null
	fi

	rm -rf "${PORTAGE_BUILDDIR}/image" "${PORTAGE_BUILDDIR}/homedir"
	rm -f "${PORTAGE_BUILDDIR}/.installed"

	if [[ $EMERGE_FROM = binary ]] || \
		! hasq keeptemp $FEATURES && ! hasq keepwork $FEATURES ; then
		rm -rf "${T}"
	fi

	if [[ $EMERGE_FROM = binary ]] || ! hasq keepwork $FEATURES; then
		rm -f "$PORTAGE_BUILDDIR"/.{ebuild_changed,logid,pretended,setuped,unpacked,prepared} \
			"$PORTAGE_BUILDDIR"/.{configured,compiled,tested,packaged} \
			"$PORTAGE_BUILDDIR"/.die_hooks \
			"$PORTAGE_BUILDDIR"/.ipc_{in,out,lock} \
			"$PORTAGE_BUILDDIR"/.exit_status

		rm -rf "${PORTAGE_BUILDDIR}/build-info"
		rm -rf "${WORKDIR}"
	fi

	if [ -f "${PORTAGE_BUILDDIR}/.unpacked" ]; then
		find "${PORTAGE_BUILDDIR}" -type d ! -regex "^${WORKDIR}" | sort -r | tr "\n" "\0" | $XARGS -0 rmdir &>/dev/null
	fi

	# do not bind this to doebuild defined DISTDIR; don't trust doebuild, and if mistakes are made it'll
	# result in it wiping the users distfiles directory (bad).
	rm -rf "${PORTAGE_BUILDDIR}/distdir"

	# Some kernels, such as Solaris, return EINVAL when an attempt
	# is made to remove the current working directory.
	cd "$PORTAGE_BUILDDIR"/../..
	rmdir "$PORTAGE_BUILDDIR" "${PORTAGE_BUILDDIR%/*}" 2>/dev/null

	true
}

into() {
	if [ "$1" == "/" ]; then
		export DESTTREE=""
	else
		export DESTTREE=$1
		if [ ! -d "${D}${DESTTREE}" ]; then
			install -d "${D}${DESTTREE}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				helpers_die "${FUNCNAME[0]} failed"
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
		if [ ! -d "${D}${INSDESTTREE}" ]; then
			install -d "${D}${INSDESTTREE}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				helpers_die "${FUNCNAME[0]} failed"
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
		if [ ! -d "${D}${_E_EXEDESTTREE_}" ]; then
			install -d "${D}${_E_EXEDESTTREE_}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				helpers_die "${FUNCNAME[0]} failed"
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
		if [ ! -d "${D}usr/share/doc/${PF}/${_E_DOCDESTTREE_}" ]; then
			install -d "${D}usr/share/doc/${PF}/${_E_DOCDESTTREE_}"
			local ret=$?
			if [[ $ret -ne 0 ]] ; then
				helpers_die "${FUNCNAME[0]} failed"
				return $ret
			fi
		fi
	fi
}

insopts() {
	export INSOPTIONS="$@"

	# `install` should never be called with '-s' ...
	hasq -s ${INSOPTIONS} && die "Never call insopts() with -s"
}

diropts() {
	export DIROPTIONS="$@"
}

exeopts() {
	export EXEOPTIONS="$@"

	# `install` should never be called with '-s' ...
	hasq -s ${EXEOPTIONS} && die "Never call exeopts() with -s"
}

libopts() {
	export LIBOPTIONS="$@"

	# `install` should never be called with '-s' ...
	hasq -s ${LIBOPTIONS} && die "Never call libopts() with -s"
}

docompress() {
	hasq "${EAPI}" 0 1 2 3 && die "'docompress' not supported in this EAPI"

	local f g
	if [[ $1 = "-x" ]]; then
		shift
		for f; do
			f=$(strip_duplicate_slashes "${f}"); f=${f%/}
			[[ ${f:0:1} = / ]] || f="/${f}"
			for g in "${PORTAGE_DOCOMPRESS_SKIP[@]}"; do
				[[ ${f} = "${g}" ]] && continue 2
			done
			PORTAGE_DOCOMPRESS_SKIP[${#PORTAGE_DOCOMPRESS_SKIP[@]}]=${f}
		done
	else
		for f; do
			f=$(strip_duplicate_slashes "${f}"); f=${f%/}
			[[ ${f:0:1} = / ]] || f="/${f}"
			for g in "${PORTAGE_DOCOMPRESS[@]}"; do
				[[ ${f} = "${g}" ]] && continue 2
			done
			PORTAGE_DOCOMPRESS[${#PORTAGE_DOCOMPRESS[@]}]=${f}
		done
	fi
}

abort_handler() {
	local msg
	if [ "$2" != "fail" ]; then
		msg="${EBUILD}: ${1} aborted; exiting."
	else
		msg="${EBUILD}: ${1} failed; exiting."
	fi
	echo
	echo "$msg"
	echo
	eval ${3}
	#unset signal handler
	trap - SIGINT SIGQUIT
}

abort_prepare() {
	abort_handler src_prepare $1
	rm -f "$PORTAGE_BUILDDIR/.prepared"
	exit 1
}

abort_configure() {
	abort_handler src_configure $1
	rm -f "$PORTAGE_BUILDDIR/.configured"
	exit 1
}

abort_compile() {
	abort_handler "src_compile" $1
	rm -f "${PORTAGE_BUILDDIR}/.compiled"
	exit 1
}

abort_test() {
	abort_handler "dyn_test" $1
	rm -f "${PORTAGE_BUILDDIR}/.tested"
	exit 1
}

abort_install() {
	abort_handler "src_install" $1
	rm -rf "${PORTAGE_BUILDDIR}/image"
	exit 1
}

has_phase_defined_up_to() {
	local phase
	for phase in unpack prepare configure compile install; do
		has ${phase} ${DEFINED_PHASES} && return 0
		[[ ${phase} == $1 ]] && return 1
	done
	# We shouldn't actually get here
	return 1
}

dyn_prepare() {

	if [[ -e $PORTAGE_BUILDDIR/.prepared ]] ; then
		vecho ">>> It appears that '$PF' is already prepared; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.prepared' to force prepare."
		return 0
	fi

	if [[ -d $S ]] ; then
		cd "${S}"
	elif hasq $EAPI 0 1 2 3 3_pre2 ; then
		cd "${WORKDIR}"
	elif [[ -z ${A} ]] && ! has_phase_defined_up_to prepare; then
		cd "${WORKDIR}"
	else
		die "The source directory '${S}' doesn't exist"
	fi

	trap abort_prepare SIGINT SIGQUIT

	ebuild_phase pre_src_prepare
	vecho ">>> Preparing source in $PWD ..."
	ebuild_phase src_prepare
	>> "$PORTAGE_BUILDDIR/.prepared" || \
		die "Failed to create $PORTAGE_BUILDDIR/.prepared"
	vecho ">>> Source prepared."
	ebuild_phase post_src_prepare

	trap - SIGINT SIGQUIT
}

dyn_configure() {

	if [[ -e $PORTAGE_BUILDDIR/.configured ]] ; then
		vecho ">>> It appears that '$PF' is already configured; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.configured' to force configuration."
		return 0
	fi

	if [[ -d $S ]] ; then
		cd "${S}"
	elif hasq $EAPI 0 1 2 3 3_pre2 ; then
		cd "${WORKDIR}"
	elif [[ -z ${A} ]] && ! has_phase_defined_up_to configure; then
		cd "${WORKDIR}"
	else
		die "The source directory '${S}' doesn't exist"
	fi

	trap abort_configure SIGINT SIGQUIT

	ebuild_phase pre_src_configure

	vecho ">>> Configuring source in $PWD ..."
	ebuild_phase src_configure
	>> "$PORTAGE_BUILDDIR/.configured" || \
		die "Failed to create $PORTAGE_BUILDDIR/.configured"
	vecho ">>> Source configured."

	ebuild_phase post_src_configure

	trap - SIGINT SIGQUIT
}

dyn_compile() {

	if [[ -e $PORTAGE_BUILDDIR/.compiled ]] ; then
		vecho ">>> It appears that '${PF}' is already compiled; skipping."
		vecho ">>> Remove '$PORTAGE_BUILDDIR/.compiled' to force compilation."
		return 0
	fi

	if [[ -d $S ]] ; then
		cd "${S}"
	elif hasq $EAPI 0 1 2 3 3_pre2 ; then
		cd "${WORKDIR}"
	elif [[ -z ${A} ]] && ! has_phase_defined_up_to compile; then
		cd "${WORKDIR}"
	else
		die "The source directory '${S}' doesn't exist"
	fi

	trap abort_compile SIGINT SIGQUIT

	ebuild_phase pre_src_compile

	vecho ">>> Compiling source in $PWD ..."
	ebuild_phase src_compile
	>> "$PORTAGE_BUILDDIR/.compiled" || \
		die "Failed to create $PORTAGE_BUILDDIR/.compiled"
	vecho ">>> Source compiled."

	ebuild_phase post_src_compile

	trap - SIGINT SIGQUIT
}

dyn_test() {

	if [[ -e $PORTAGE_BUILDDIR/.tested ]] ; then
		vecho ">>> It appears that ${PN} has already been tested; skipping."
		vecho ">>> Remove '${PORTAGE_BUILDDIR}/.tested' to force test."
		return
	fi

	if [ "${EBUILD_FORCE_TEST}" == "1" ] ; then
		# If USE came from ${T}/environment then it might not have USE=test
		# like it's supposed to here.
		! hasq test ${USE} && export USE="${USE} test"
	fi

	trap "abort_test" SIGINT SIGQUIT
	if [ -d "${S}" ]; then
		cd "${S}"
	else
		cd "${WORKDIR}"
	fi

	if ! hasq test $FEATURES && [ "${EBUILD_FORCE_TEST}" != "1" ]; then
		vecho ">>> Test phase [not enabled]: ${CATEGORY}/${PF}"
	elif hasq test $RESTRICT; then
		einfo "Skipping make test/check due to ebuild restriction."
		vecho ">>> Test phase [explicitly disabled]: ${CATEGORY}/${PF}"
	else
		local save_sp=${SANDBOX_PREDICT}
		addpredict /
		ebuild_phase pre_src_test
		ebuild_phase src_test
		>> "$PORTAGE_BUILDDIR/.tested" || \
			die "Failed to create $PORTAGE_BUILDDIR/.tested"
		ebuild_phase post_src_test
		SANDBOX_PREDICT=${save_sp}
	fi

	trap - SIGINT SIGQUIT
}

dyn_install() {
	[ -z "$PORTAGE_BUILDDIR" ] && die "${FUNCNAME}: PORTAGE_BUILDDIR is unset"
	if hasq noauto $FEATURES ; then
		rm -f "${PORTAGE_BUILDDIR}/.installed"
	elif [[ -e $PORTAGE_BUILDDIR/.installed ]] ; then
		vecho ">>> It appears that '${PF}' is already installed; skipping."
		vecho ">>> Remove '${PORTAGE_BUILDDIR}/.installed' to force install."
		return 0
	fi
	trap "abort_install" SIGINT SIGQUIT
	ebuild_phase pre_src_install
	rm -rf "${PORTAGE_BUILDDIR}/image"
	mkdir "${PORTAGE_BUILDDIR}/image"
	if [[ -d $S ]] ; then
		cd "${S}"
	elif hasq $EAPI 0 1 2 3 3_pre2 ; then
		cd "${WORKDIR}"
	elif [[ -z ${A} ]] && ! has_phase_defined_up_to install; then
		cd "${WORKDIR}"
	else
		die "The source directory '${S}' doesn't exist"
	fi

	vecho
	vecho ">>> Install ${PF} into ${D} category ${CATEGORY}"
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D

	# Reset exeinto(), docinto(), insinto(), and into() state variables
	# in case the user is running the install phase multiple times
	# consecutively via the ebuild command.
	export DESTTREE=/usr
	export INSDESTTREE=""
	export _E_EXEDESTTREE_=""
	export _E_DOCDESTTREE_=""

	ebuild_phase src_install
	>> "$PORTAGE_BUILDDIR/.installed" || \
		die "Failed to create $PORTAGE_BUILDDIR/.installed"
	vecho ">>> Completed installing ${PF} into ${D}"
	vecho
	ebuild_phase post_src_install

	cd "${PORTAGE_BUILDDIR}"/build-info
	set -f
	local f x
	IFS=$' \t\n\r'
	for f in CATEGORY DEFINED_PHASES FEATURES INHERITED IUSE REQUIRED_USE \
		PF PKGUSE SLOT KEYWORDS HOMEPAGE DESCRIPTION ; do
		x=$(echo -n ${!f})
		[[ -n $x ]] && echo "$x" > $f
	done
	if [[ $CATEGORY != virtual ]] ; then
		for f in ASFLAGS CBUILD CC CFLAGS CHOST CTARGET CXX \
			CXXFLAGS EXTRA_ECONF EXTRA_EINSTALL EXTRA_MAKE \
			LDFLAGS LIBCFLAGS LIBCXXFLAGS ; do
			x=$(echo -n ${!f})
			[[ -n $x ]] && echo "$x" > $f
		done
	fi
	echo "${USE}"       > USE
	echo "${EAPI:-0}"   > EAPI
	set +f

	# local variables can leak into the saved environment.
	unset f

	save_ebuild_env --exclude-init-phases | filter_readonly_variables \
		--filter-path --filter-sandbox --allow-extra-vars > environment
	assert "save_ebuild_env failed"

	${PORTAGE_BZIP2_COMMAND} -f9 environment

	cp "${EBUILD}" "${PF}.ebuild"
	[ -n "${PORTAGE_REPO_NAME}" ]  && echo "${PORTAGE_REPO_NAME}" > repository
	if hasq nostrip ${FEATURES} ${RESTRICT} || hasq strip ${RESTRICT}
	then
		>> DEBUGBUILD
	fi
	trap - SIGINT SIGQUIT
}

dyn_preinst() {
	if [ -z "${D}" ]; then
		eerror "${FUNCNAME}: D is unset"
		return 1
	fi
	ebuild_phase_with_hooks pkg_preinst
}

dyn_help() {
	echo
	echo "Portage"
	echo "Copyright 1999-2010 Gentoo Foundation"
	echo
	echo "How to use the ebuild command:"
	echo
	echo "The first argument to ebuild should be an existing .ebuild file."
	echo
	echo "One or more of the following options can then be specified.  If more"
	echo "than one option is specified, each will be executed in order."
	echo
	echo "  help        : show this help screen"
	echo "  pretend     : execute package specific pretend actions"
	echo "  setup       : execute package specific setup actions"
	echo "  fetch       : download source archive(s) and patches"
	echo "  digest      : create a manifest file for the package"
	echo "  manifest    : create a manifest file for the package"
	echo "  unpack      : unpack sources (auto-dependencies if needed)"
	echo "  prepare     : prepare sources (auto-dependencies if needed)"
	echo "  configure   : configure sources (auto-fetch/unpack if needed)"
	echo "  compile     : compile sources (auto-fetch/unpack/configure if needed)"
	echo "  test        : test package (auto-fetch/unpack/configure/compile if needed)"
	echo "  preinst     : execute pre-install instructions"
	echo "  postinst    : execute post-install instructions"
	echo "  install     : install the package to the temporary install directory"
	echo "  qmerge      : merge image into live filesystem, recording files in db"
	echo "  merge       : do fetch, unpack, compile, install and qmerge"
	echo "  prerm       : execute pre-removal instructions"
	echo "  postrm      : execute post-removal instructions"
	echo "  unmerge     : remove package from live filesystem"
	echo "  config      : execute package specific configuration actions"
	echo "  package     : create a tarball package in ${PKGDIR}/All"
	echo "  rpm         : build a RedHat RPM package"
	echo "  clean       : clean up all source and temporary files"
	echo
	echo "The following settings will be used for the ebuild process:"
	echo
	echo "  package     : ${PF}"
	echo "  slot        : ${SLOT}"
	echo "  category    : ${CATEGORY}"
	echo "  description : ${DESCRIPTION}"
	echo "  system      : ${CHOST}"
	echo "  c flags     : ${CFLAGS}"
	echo "  c++ flags   : ${CXXFLAGS}"
	echo "  make flags  : ${MAKEOPTS}"
	echo -n "  build mode  : "
	if hasq nostrip ${FEATURES} ${RESTRICT} || hasq strip ${RESTRICT} ;
	then
		echo "debug (large)"
	else
		echo "production (stripped)"
	fi
	echo "  merge to    : ${ROOT}"
	echo
	if [ -n "$USE" ]; then
		echo "Additionally, support for the following optional features will be enabled:"
		echo
		echo "  ${USE}"
	fi
	echo
}

# debug-print() gets called from many places with verbose status information useful
# for tracking down problems. The output is in $T/eclass-debug.log.
# You can set ECLASS_DEBUG_OUTPUT to redirect the output somewhere else as well.
# The special "on" setting echoes the information, mixing it with the rest of the
# emerge output.
# You can override the setting by exporting a new one from the console, or you can
# set a new default in make.*. Here the default is "" or unset.

# in the future might use e* from /etc/init.d/functions.sh if i feel like it
debug-print() {
	# if $T isn't defined, we're in dep calculation mode and
	# shouldn't do anything
	[[ $EBUILD_PHASE = depend || ! -d ${T} || ${#} -eq 0 ]] && return 0

	if [[ ${ECLASS_DEBUG_OUTPUT} == on ]]; then
		printf 'debug: %s\n' "${@}" >&2
	elif [[ -n ${ECLASS_DEBUG_OUTPUT} ]]; then
		printf 'debug: %s\n' "${@}" >> "${ECLASS_DEBUG_OUTPUT}"
	fi

	if [[ -w $T ]] ; then
		# default target
		printf '%s\n' "${@}" >> "${T}/eclass-debug.log"
		# let the portage user own/write to this file
		chgrp portage "${T}/eclass-debug.log" &>/dev/null
		chmod g+w "${T}/eclass-debug.log" &>/dev/null
	fi
}

# The following 2 functions are debug-print() wrappers

debug-print-function() {
	debug-print "${1}: entering function, parameters: ${*:2}"
}

debug-print-section() {
	debug-print "now in section ${*}"
}

# Sources all eclasses in parameters
declare -ix ECLASS_DEPTH=0
inherit() {
	ECLASS_DEPTH=$(($ECLASS_DEPTH + 1))
	if [[ ${ECLASS_DEPTH} > 1 ]]; then
		debug-print "*** Multiple Inheritence (Level: ${ECLASS_DEPTH})"
	fi

	if [[ -n $ECLASS && -n ${!__export_funcs_var} ]] ; then
		echo "QA Notice: EXPORT_FUNCTIONS is called before inherit in" \
			"$ECLASS.eclass. For compatibility with <=portage-2.1.6.7," \
			"only call EXPORT_FUNCTIONS after inherit(s)." \
			| fmt -w 75 | while read -r ; do eqawarn "$REPLY" ; done
	fi

	local location
	local olocation
	local x

	# These variables must be restored before returning.
	local PECLASS=$ECLASS
	local prev_export_funcs_var=$__export_funcs_var

	local B_IUSE
	local B_REQUIRED_USE
	local B_DEPEND
	local B_RDEPEND
	local B_PDEPEND
	while [ "$1" ]; do
		location="${ECLASSDIR}/${1}.eclass"
		olocation=""

		export ECLASS="$1"
		__export_funcs_var=__export_functions_$ECLASS_DEPTH
		unset $__export_funcs_var

		if [ "${EBUILD_PHASE}" != "depend" ] && \
			[[ ${EBUILD_PHASE} != *rm ]] && \
			[[ ${EMERGE_FROM} != "binary" ]] ; then
			# This is disabled in the *rm phases because they frequently give
			# false alarms due to INHERITED in /var/db/pkg being outdated
			# in comparison the the eclasses from the portage tree.
			if ! hasq $ECLASS $INHERITED; then
				eqawarn "QA Notice: ECLASS '$ECLASS' inherited illegally in $CATEGORY/$PF $EBUILD_PHASE"
			fi
		fi

		# any future resolution code goes here
		if [ -n "$PORTDIR_OVERLAY" ]; then
			local overlay
			for overlay in ${PORTDIR_OVERLAY}; do
				olocation="${overlay}/eclass/${1}.eclass"
				if [ -e "$olocation" ]; then
					location="${olocation}"
					debug-print "  eclass exists: ${location}"
				fi
			done
		fi
		debug-print "inherit: $1 -> $location"
		[ ! -e "$location" ] && die "${1}.eclass could not be found by inherit()"

		if [ "${location}" == "${olocation}" ] && \
			! hasq "${location}" ${EBUILD_OVERLAY_ECLASSES} ; then
				EBUILD_OVERLAY_ECLASSES="${EBUILD_OVERLAY_ECLASSES} ${location}"
		fi

		#We need to back up the value of DEPEND and RDEPEND to B_DEPEND and B_RDEPEND
		#(if set).. and then restore them after the inherit call.

		#turn off glob expansion
		set -f

		# Retain the old data and restore it later.
		unset B_IUSE B_REQUIRED_USE B_DEPEND B_RDEPEND B_PDEPEND
		[ "${IUSE+set}"       = set ] && B_IUSE="${IUSE}"
		[ "${REQUIRED_USE+set}" = set ] && B_REQUIRED_USE="${REQUIRED_USE}"
		[ "${DEPEND+set}"     = set ] && B_DEPEND="${DEPEND}"
		[ "${RDEPEND+set}"    = set ] && B_RDEPEND="${RDEPEND}"
		[ "${PDEPEND+set}"    = set ] && B_PDEPEND="${PDEPEND}"
		unset IUSE REQUIRED_USE DEPEND RDEPEND PDEPEND
		#turn on glob expansion
		set +f

		qa_source "$location" || die "died sourcing $location in inherit()"
		
		#turn off glob expansion
		set -f

		# If each var has a value, append it to the global variable E_* to
		# be applied after everything is finished. New incremental behavior.
		[ "${IUSE+set}"       = set ] && export E_IUSE="${E_IUSE} ${IUSE}"
		[ "${REQUIRED_USE+set}"       = set ] && export E_REQUIRED_USE="${E_REQUIRED_USE} ${REQUIRED_USE}"
		[ "${DEPEND+set}"     = set ] && export E_DEPEND="${E_DEPEND} ${DEPEND}"
		[ "${RDEPEND+set}"    = set ] && export E_RDEPEND="${E_RDEPEND} ${RDEPEND}"
		[ "${PDEPEND+set}"    = set ] && export E_PDEPEND="${E_PDEPEND} ${PDEPEND}"

		[ "${B_IUSE+set}"     = set ] && IUSE="${B_IUSE}"
		[ "${B_IUSE+set}"     = set ] || unset IUSE
		
		[ "${B_REQUIRED_USE+set}"     = set ] && REQUIRED_USE="${B_REQUIRED_USE}"
		[ "${B_REQUIRED_USE+set}"     = set ] || unset REQUIRED_USE

		[ "${B_DEPEND+set}"   = set ] && DEPEND="${B_DEPEND}"
		[ "${B_DEPEND+set}"   = set ] || unset DEPEND

		[ "${B_RDEPEND+set}"  = set ] && RDEPEND="${B_RDEPEND}"
		[ "${B_RDEPEND+set}"  = set ] || unset RDEPEND

		[ "${B_PDEPEND+set}"  = set ] && PDEPEND="${B_PDEPEND}"
		[ "${B_PDEPEND+set}"  = set ] || unset PDEPEND

		#turn on glob expansion
		set +f

		if [[ -n ${!__export_funcs_var} ]] ; then
			for x in ${!__export_funcs_var} ; do
				debug-print "EXPORT_FUNCTIONS: $x -> ${ECLASS}_$x"
				declare -F "${ECLASS}_$x" >/dev/null || \
					die "EXPORT_FUNCTIONS: ${ECLASS}_$x is not defined"
				eval "$x() { ${ECLASS}_$x \"\$@\" ; }" > /dev/null
			done
		fi
		unset $__export_funcs_var

		hasq $1 $INHERITED || export INHERITED="$INHERITED $1"

		shift
	done
	((--ECLASS_DEPTH)) # Returns 1 when ECLASS_DEPTH reaches 0.
	if (( ECLASS_DEPTH > 0 )) ; then
		export ECLASS=$PECLASS
		__export_funcs_var=$prev_export_funcs_var
	else
		unset ECLASS __export_funcs_var
	fi
	return 0
}

# Exports stub functions that call the eclass's functions, thereby making them default.
# For example, if ECLASS="base" and you call "EXPORT_FUNCTIONS src_unpack", the following
# code will be eval'd:
# src_unpack() { base_src_unpack; }
EXPORT_FUNCTIONS() {
	if [ -z "$ECLASS" ]; then
		die "EXPORT_FUNCTIONS without a defined ECLASS"
	fi
	eval $__export_funcs_var+=\" $*\"
}

# this is a function for removing any directory matching a passed in pattern from
# PATH
remove_path_entry() {
	save_IFS
	IFS=":"
	stripped_path="${PATH}"
	while [ -n "$1" ]; do
		cur_path=""
		for p in ${stripped_path}; do
			if [ "${p/${1}}" == "${p}" ]; then
				cur_path="${cur_path}:${p}"
			fi
		done
		stripped_path="${cur_path#:*}"
		shift
	done
	restore_IFS
	PATH="${stripped_path}"
}

# @FUNCTION: _ebuild_arg_to_phase
# @DESCRIPTION:
# Translate a known ebuild(1) argument into the precise
# name of it's corresponding ebuild phase.
_ebuild_arg_to_phase() {
	[ $# -ne 2 ] && die "expected exactly 2 args, got $#: $*"
	local eapi=$1
	local arg=$2
	local phase_func=""

	case "$arg" in
		pretend)
			! hasq $eapi 0 1 2 3 3_pre2 && \
				phase_func=pkg_pretend
			;;
		setup)
			phase_func=pkg_setup
			;;
		nofetch)
			phase_func=pkg_nofetch
			;;
		unpack)
			phase_func=src_unpack
			;;
		prepare)
			! hasq $eapi 0 1 && \
				phase_func=src_prepare
			;;
		configure)
			! hasq $eapi 0 1 && \
				phase_func=src_configure
			;;
		compile)
			phase_func=src_compile
			;;
		test)
			phase_func=src_test
			;;
		install)
			phase_func=src_install
			;;
		preinst)
			phase_func=pkg_preinst
			;;
		postinst)
			phase_func=pkg_postinst
			;;
		prerm)
			phase_func=pkg_prerm
			;;
		postrm)
			phase_func=pkg_postrm
			;;
	esac

	[[ -z $phase_func ]] && return 1
	echo "$phase_func"
	return 0
}

_ebuild_phase_funcs() {
	[ $# -ne 2 ] && die "expected exactly 2 args, got $#: $*"
	local eapi=$1
	local phase_func=$2
	local default_phases="pkg_nofetch src_unpack src_prepare src_configure
		src_compile src_install src_test"
	local x y default_func=""

	for x in pkg_nofetch src_unpack src_test ; do
		declare -F $x >/dev/null || \
			eval "$x() { _eapi0_$x \"\$@\" ; }"
	done

	case $eapi in

		0|1)

			if ! declare -F src_compile >/dev/null ; then
				case $eapi in
					0)
						src_compile() { _eapi0_src_compile "$@" ; }
						;;
					*)
						src_compile() { _eapi1_src_compile "$@" ; }
						;;
				esac
			fi

			for x in $default_phases ; do
				eval "default_$x() {
					die \"default_$x() is not supported with EAPI='$eapi' during phase $phase_func\"
				}"
			done

			eval "default() {
				die \"default() is not supported with EAPI='$eapi' during phase $phase_func\"
			}"

			;;

		*)

			declare -F src_configure >/dev/null || \
				src_configure() { _eapi2_src_configure "$@" ; }

			declare -F src_compile >/dev/null || \
				src_compile() { _eapi2_src_compile "$@" ; }

			has $eapi 2 3 3_pre2 || declare -F src_install >/dev/null || \
				src_install() { _eapi4_src_install "$@" ; }

			if hasq $phase_func $default_phases ; then

				_eapi2_pkg_nofetch   () { _eapi0_pkg_nofetch          "$@" ; }
				_eapi2_src_unpack    () { _eapi0_src_unpack           "$@" ; }
				_eapi2_src_prepare   () { true                             ; }
				_eapi2_src_test      () { _eapi0_src_test             "$@" ; }
				_eapi2_src_install   () { die "$FUNCNAME is not supported" ; }

				for x in $default_phases ; do
					eval "default_$x() { _eapi2_$x \"\$@\" ; }"
				done

				eval "default() { _eapi2_$phase_func \"\$@\" ; }"

				case $eapi in
					2|3)
						;;
					*)
						eval "default_src_install() { _eapi4_src_install \"\$@\" ; }"
						[[ $phase_func = src_install ]] && \
							eval "default() { _eapi4_$phase_func \"\$@\" ; }"
						;;
				esac

			else

				for x in $default_phases ; do
					eval "default_$x() {
						die \"default_$x() is not supported in phase $default_func\"
					}"
				done

				eval "default() {
					die \"default() is not supported with EAPI='$eapi' during phase $phase_func\"
				}"

			fi

			;;
	esac
}

PORTAGE_BASHRCS_SOURCED=0

# @FUNCTION: source_all_bashrcs
# @DESCRIPTION:
# Source a relevant bashrc files and perform other miscellaneous
# environment initialization when appropriate.
#
# If EAPI is set then define functions provided by the current EAPI:
#
#  * default_* aliases for the current EAPI phase functions
#  * A "default" function which is an alias for the default phase
#    function for the current phase.
#
source_all_bashrcs() {
	[[ $PORTAGE_BASHRCS_SOURCED = 1 ]] && return 0
	PORTAGE_BASHRCS_SOURCED=1
	local x

	local OCC="${CC}" OCXX="${CXX}"

	if [[ $EBUILD_PHASE != depend ]] ; then
		# source the existing profile.bashrcs.
		save_IFS
		IFS=$'\n'
		local path_array=($PROFILE_PATHS)
		restore_IFS
		for x in "${path_array[@]}" ; do
			[ -f "$x/profile.bashrc" ] && qa_source "$x/profile.bashrc"
		done
	fi

	# We assume if people are changing shopts in their bashrc they do so at their
	# own peril.  This is the ONLY non-portage bit of code that can change shopts
	# without a QA violation.
	for x in "${PORTAGE_BASHRC}" "${PM_EBUILD_HOOK_DIR}"/${CATEGORY}/{${PN},${PN}:${SLOT},${P},${PF}}; do
		if [ -r "${x}" ]; then
			# If $- contains x, then tracing has already enabled elsewhere for some
			# reason.  We preserve it's state so as not to interfere.
			if [ "$PORTAGE_DEBUG" != "1" ] || [ "${-/x/}" != "$-" ]; then
				source "${x}"
			else
				set -x
				source "${x}"
				set +x
			fi
		fi
	done

	[ ! -z "${OCC}" ] && export CC="${OCC}"
	[ ! -z "${OCXX}" ] && export CXX="${OCXX}"
}

# Hardcoded bash lists are needed for backward compatibility with
# <portage-2.1.4 since they assume that a newly installed version
# of ebuild.sh will work for pkg_postinst, pkg_prerm, and pkg_postrm
# when portage is upgrading itself.

PORTAGE_READONLY_METADATA="DEFINED_PHASES DEPEND DESCRIPTION
	EAPI HOMEPAGE INHERITED IUSE REQUIRED_USE KEYWORDS LICENSE
	PDEPEND PROVIDE RDEPEND RESTRICT SLOT SRC_URI"

PORTAGE_READONLY_VARS="D EBUILD EBUILD_PHASE \
	EBUILD_SH_ARGS ECLASSDIR EMERGE_FROM FILESDIR MERGE_TYPE \
	PM_EBUILD_HOOK_DIR \
	PORTAGE_ACTUAL_DISTDIR PORTAGE_ARCHLIST PORTAGE_BASHRC  \
	PORTAGE_BINPKG_FILE PORTAGE_BINPKG_TAR_OPTS PORTAGE_BINPKG_TMPFILE \
	PORTAGE_BIN_PATH PORTAGE_BUILDDIR PORTAGE_BUNZIP2_COMMAND \
	PORTAGE_BZIP2_COMMAND PORTAGE_COLORMAP PORTAGE_CONFIGROOT \
	PORTAGE_DEBUG PORTAGE_DEPCACHEDIR PORTAGE_EBUILD_EXIT_FILE \
	PORTAGE_GID PORTAGE_GRPNAME PORTAGE_INST_GID PORTAGE_INST_UID \
	PORTAGE_IPC_DAEMON PORTAGE_IUSE PORTAGE_LOG_FILE \
	PORTAGE_MUTABLE_FILTERED_VARS PORTAGE_PYM_PATH PORTAGE_PYTHON \
	PORTAGE_READONLY_METADATA PORTAGE_READONLY_VARS \
	PORTAGE_REPO_NAME PORTAGE_RESTRICT PORTAGE_SANDBOX_COMPAT_LEVEL \
	PORTAGE_SAVED_READONLY_VARS PORTAGE_SIGPIPE_STATUS \
	PORTAGE_TMPDIR PORTAGE_UPDATE_ENV PORTAGE_USERNAME \
	PORTAGE_VERBOSE PORTAGE_WORKDIR_MODE PORTDIR PORTDIR_OVERLAY \
	PROFILE_PATHS REPLACING_VERSIONS REPLACED_BY_VERSION T WORKDIR"

PORTAGE_SAVED_READONLY_VARS="A CATEGORY P PF PN PR PV PVR"

# Variables that portage sets but doesn't mark readonly.
# In order to prevent changed values from causing unexpected
# interference, they are filtered out of the environment when
# it is saved or loaded (any mutations do not persist).
PORTAGE_MUTABLE_FILTERED_VARS="AA HOSTNAME"

# @FUNCTION: filter_readonly_variables
# @DESCRIPTION: [--filter-sandbox] [--allow-extra-vars]
# Read an environment from stdin and echo to stdout while filtering variables
# with names that are known to cause interference:
#
#   * some specific variables for which bash does not allow assignment
#   * some specific variables that affect portage or sandbox behavior
#   * variable names that begin with a digit or that contain any
#     non-alphanumeric characters that are not be supported by bash
#
# --filter-sandbox causes all SANDBOX_* variables to be filtered, which
# is only desired in certain cases, such as during preprocessing or when
# saving environment.bz2 for a binary or installed package.
#
# --filter-features causes the special FEATURES variable to be filtered.
# Generally, we want it to persist between phases since the user might
# want to modify it via bashrc to enable things like splitdebug and
# installsources for specific packages. They should be able to modify it
# in pre_pkg_setup() and have it persist all the way through the install
# phase. However, if FEATURES exist inside environment.bz2 then they
# should be overridden by current settings.
#
# --filter-locale causes locale related variables such as LANG and LC_*
# variables to be filtered. These variables should persist between phases,
# in case they are modified by the ebuild. However, the current user
# settings should be used when loading the environment from a binary or
# installed package.
#
# --filter-path causes the PATH variable to be filtered. This variable
# should persist between phases, in case it is modified by the ebuild.
# However, old settings should be overridden when loading the
# environment from a binary or installed package.
#
# ---allow-extra-vars causes some extra vars to be allowd through, such
# as ${PORTAGE_SAVED_READONLY_VARS} and ${PORTAGE_MUTABLE_FILTERED_VARS}.
#
# In bash-3.2_p20+ an attempt to assign BASH_*, FUNCNAME, GROUPS or any
# readonly variable cause the shell to exit while executing the "source"
# builtin command. To avoid this problem, this function filters those
# variables out and discards them. See bug #190128.
filter_readonly_variables() {
	local x filtered_vars
	local readonly_bash_vars="BASHOPTS BASHPID DIRSTACK EUID
		FUNCNAME GROUPS PIPESTATUS PPID SHELLOPTS UID"
	local bash_misc_vars="BASH BASH_.* COMP_WORDBREAKS HISTCMD
		HISTFILE HOSTNAME HOSTTYPE IFS LINENO MACHTYPE OLDPWD
		OPTERR OPTIND OSTYPE POSIXLY_CORRECT PS4 PWD RANDOM
		SECONDS SHELL SHLVL"
	local filtered_sandbox_vars="SANDBOX_ACTIVE SANDBOX_BASHRC
		SANDBOX_DEBUG_LOG SANDBOX_DISABLED SANDBOX_LIB
		SANDBOX_LOG SANDBOX_ON"
	local misc_garbage_vars="_portage_filter_opts"
	filtered_vars="$readonly_bash_vars $bash_misc_vars
		$PORTAGE_READONLY_VARS $misc_garbage_vars"

	# Don't filter/interfere with prefix variables unless they are
	# supported by the current EAPI.
	case "${EAPI:-0}" in
		0|1|2)
			;;
		*)
			filtered_vars+=" ED EPREFIX EROOT"
			;;
	esac

	if hasq --filter-sandbox $* ; then
		filtered_vars="${filtered_vars} SANDBOX_.*"
	else
		filtered_vars="${filtered_vars} ${filtered_sandbox_vars}"
	fi
	if hasq --filter-features $* ; then
		filtered_vars="${filtered_vars} FEATURES PORTAGE_FEATURES"
	fi
	if hasq --filter-path $* ; then
		filtered_vars+=" PATH"
	fi
	if hasq --filter-locale $* ; then
		filtered_vars+=" LANG LC_ALL LC_COLLATE
			LC_CTYPE LC_MESSAGES LC_MONETARY
			LC_NUMERIC LC_PAPER LC_TIME"
	fi
	if ! hasq --allow-extra-vars $* ; then
		filtered_vars="
			${filtered_vars}
			${PORTAGE_SAVED_READONLY_VARS}
			${PORTAGE_MUTABLE_FILTERED_VARS}
		"
	fi

	"${PORTAGE_PYTHON:-/usr/bin/python}" "${PORTAGE_BIN_PATH}"/filter-bash-environment.py "${filtered_vars}" || die "filter-bash-environment.py failed"
}

# @FUNCTION: preprocess_ebuild_env
# @DESCRIPTION:
# Filter any readonly variables from ${T}/environment, source it, and then
# save it via save_ebuild_env(). This process should be sufficient to prevent
# any stale variables or functions from an arbitrary environment from
# interfering with the current environment. This is useful when an existing
# environment needs to be loaded from a binary or installed package.
preprocess_ebuild_env() {
	local _portage_filter_opts=""
	if [ -f "${T}/environment.raw" ] ; then
		# This is a signal from the python side, indicating that the
		# environment may contain stale SANDBOX_{DENY,PREDICT,READ,WRITE}
		# and FEATURES variables that should be filtered out. Between
		# phases, these variables are normally preserved.
		_portage_filter_opts+=" --filter-features --filter-locale --filter-path --filter-sandbox"
	fi
	filter_readonly_variables $_portage_filter_opts < "${T}"/environment \
		>> "$T/environment.filtered" || return $?
	unset _portage_filter_opts
	mv "${T}"/environment.filtered "${T}"/environment || return $?
	rm -f "${T}/environment.success" || return $?
	# WARNING: Code inside this subshell should avoid making assumptions
	# about variables or functions after source "${T}"/environment has been
	# called. Any variables that need to be relied upon should already be
	# filtered out above.
	(
		export SANDBOX_ON=1
		source "${T}/environment" || exit $?
		# We have to temporarily disable sandbox since the
		# SANDBOX_{DENY,READ,PREDICT,WRITE} values we've just loaded
		# may be unusable (triggering in spurious sandbox violations)
		# until we've merged them with our current values.
		export SANDBOX_ON=0

		# It's remotely possible that save_ebuild_env() has been overridden
		# by the above source command. To protect ourselves, we override it
		# here with our own version. ${PORTAGE_BIN_PATH} is safe to use here
		# because it's already filtered above.
		source "${PORTAGE_BIN_PATH}/isolated-functions.sh" || exit $?

		# Rely on save_ebuild_env() to filter out any remaining variables
		# and functions that could interfere with the current environment.
		save_ebuild_env || exit $?
		>> "$T/environment.success" || exit $?
	) > "${T}/environment.filtered"
	local retval
	if [ -e "${T}/environment.success" ] ; then
		filter_readonly_variables --filter-features < \
			"${T}/environment.filtered" > "${T}/environment"
		retval=$?
	else
		retval=1
	fi
	rm -f "${T}"/environment.{filtered,raw,success}
	return ${retval}
}

# === === === === === === === === === === === === === === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === === === === === === === === === === === === === ===

export SANDBOX_ON="1"
export S=${WORKDIR}/${P}

unset E_IUSE E_REQUIRED_USE E_DEPEND E_RDEPEND E_PDEPEND

# Turn of extended glob matching so that g++ doesn't get incorrectly matched.
shopt -u extglob

if [[ ${EBUILD_PHASE} == depend ]] ; then
	QA_INTERCEPTORS="awk bash cc egrep equery fgrep g++
		gawk gcc grep javac java-config nawk perl
		pkg-config python python-config sed"
elif [[ ${EBUILD_PHASE} == clean* ]] ; then
	unset QA_INTERCEPTORS
else
	QA_INTERCEPTORS="autoconf automake aclocal libtoolize"
fi
# level the QA interceptors if we're in depend
if [[ -n ${QA_INTERCEPTORS} ]] ; then
	for BIN in ${QA_INTERCEPTORS}; do
		BIN_PATH=$(type -Pf ${BIN})
		if [ "$?" != "0" ]; then
			BODY="echo \"*** missing command: ${BIN}\" >&2; return 127"
		else
			BODY="${BIN_PATH} \"\$@\"; return \$?"
		fi
		if [[ ${EBUILD_PHASE} == depend ]] ; then
			FUNC_SRC="${BIN}() {
				if [ \$ECLASS_DEPTH -gt 0 ]; then
					eqawarn \"QA Notice: '${BIN}' called in global scope: eclass \${ECLASS}\"
				else
					eqawarn \"QA Notice: '${BIN}' called in global scope: \${CATEGORY}/\${PF}\"
				fi
			${BODY}
			}"
		elif hasq ${BIN} autoconf automake aclocal libtoolize ; then
			FUNC_SRC="${BIN}() {
				if ! hasq \${FUNCNAME[1]} eautoreconf eaclocal _elibtoolize \\
					eautoheader eautoconf eautomake autotools_run_tool \\
					autotools_check_macro autotools_get_subdirs \\
					autotools_get_auxdir ; then
					eqawarn \"QA Notice: '${BIN}' called by \${FUNCNAME[1]}: \${CATEGORY}/\${PF}\"
					eqawarn \"Use autotools.eclass instead of calling '${BIN}' directly.\"
				fi
			${BODY}
			}"
		else
			FUNC_SRC="${BIN}() {
				eqawarn \"QA Notice: '${BIN}' called by \${FUNCNAME[1]}: \${CATEGORY}/\${PF}\"
			${BODY}
			}"
		fi
		eval "$FUNC_SRC" || echo "error creating QA interceptor ${BIN}" >&2
	done
	unset BIN_PATH BIN BODY FUNC_SRC
fi

# Subshell/helper die support (must export for the die helper).
export EBUILD_MASTER_PID=$BASHPID
trap 'exit 1' SIGTERM

if ! hasq "$EBUILD_PHASE" clean cleanrm depend && \
	[ -f "${T}"/environment ] ; then
	# The environment may have been extracted from environment.bz2 or
	# may have come from another version of ebuild.sh or something.
	# In any case, preprocess it to prevent any potential interference.
	preprocess_ebuild_env || \
		die "error processing environment"
	# Colon separated SANDBOX_* variables need to be cumulative.
	for x in SANDBOX_DENY SANDBOX_READ SANDBOX_PREDICT SANDBOX_WRITE ; do
		export PORTAGE_${x}=${!x}
	done
	PORTAGE_SANDBOX_ON=${SANDBOX_ON}
	export SANDBOX_ON=1
	source "${T}"/environment || \
		die "error sourcing environment"
	# We have to temporarily disable sandbox since the
	# SANDBOX_{DENY,READ,PREDICT,WRITE} values we've just loaded
	# may be unusable (triggering in spurious sandbox violations)
	# until we've merged them with our current values.
	export SANDBOX_ON=0
	for x in SANDBOX_DENY SANDBOX_PREDICT SANDBOX_READ SANDBOX_WRITE ; do
		y="PORTAGE_${x}"
		if [ -z "${!x}" ] ; then
			export ${x}=${!y}
		elif [ -n "${!y}" ] && [ "${!y}" != "${!x}" ] ; then
			# filter out dupes
			export ${x}=$(printf "${!y}:${!x}" | tr ":" "\0" | \
				sort -z -u | tr "\0" ":")
		fi
		export ${x}=${!x%:}
		unset PORTAGE_${x}
	done
	unset x y
	export SANDBOX_ON=${PORTAGE_SANDBOX_ON}
	unset PORTAGE_SANDBOX_ON
	[[ -n $EAPI ]] || EAPI=0
fi

if ! hasq "$EBUILD_PHASE" clean cleanrm ; then
	if [[ $EBUILD_PHASE = depend || ! -f $T/environment || \
		-f $PORTAGE_BUILDDIR/.ebuild_changed ]] || \
		hasq noauto $FEATURES ; then
		# The bashrcs get an opportunity here to set aliases that will be expanded
		# during sourcing of ebuilds and eclasses.
		source_all_bashrcs

		# *DEPEND and IUSE will be set during the sourcing of the ebuild.
		# In order to ensure correct interaction between ebuilds and
		# eclasses, they need to be unset before this process of
		# interaction begins.
		unset DEPEND RDEPEND PDEPEND IUSE REQUIRED_USE

		if [[ $PORTAGE_DEBUG != 1 || ${-/x/} != $- ]] ; then
			source "$EBUILD" || die "error sourcing ebuild"
		else
			set -x
			source "$EBUILD" || die "error sourcing ebuild"
			set +x
		fi

		if [[ "${EBUILD_PHASE}" != "depend" ]] ; then
			RESTRICT=${PORTAGE_RESTRICT}
			[[ -e $PORTAGE_BUILDDIR/.ebuild_changed ]] && \
			rm "$PORTAGE_BUILDDIR/.ebuild_changed"
		fi

		[[ -n $EAPI ]] || EAPI=0

		if has "$EAPI" 0 1 2 3 3_pre2 ; then
			export RDEPEND=${RDEPEND-${DEPEND}}
			debug-print "RDEPEND: not set... Setting to: ${DEPEND}"
		fi

		# add in dependency info from eclasses
		IUSE="${IUSE} ${E_IUSE}"
		DEPEND="${DEPEND} ${E_DEPEND}"
		RDEPEND="${RDEPEND} ${E_RDEPEND}"
		PDEPEND="${PDEPEND} ${E_PDEPEND}"
		REQUIRED_USE="${REQUIRED_USE} ${E_REQUIRED_USE}"
		
		unset ECLASS E_IUSE E_REQUIRED_USE E_DEPEND E_RDEPEND E_PDEPEND 

		# alphabetically ordered by $EBUILD_PHASE value
		case "$EAPI" in
			0|1)
				_valid_phases="src_compile pkg_config pkg_info src_install
					pkg_nofetch pkg_postinst pkg_postrm pkg_preinst pkg_prerm
					pkg_setup src_test src_unpack"
				;;
			2|3|3_pre2)
				_valid_phases="src_compile pkg_config src_configure pkg_info
					src_install pkg_nofetch pkg_postinst pkg_postrm pkg_preinst
					src_prepare pkg_prerm pkg_setup src_test src_unpack"
				;;
			*)
				_valid_phases="src_compile pkg_config src_configure pkg_info
					src_install pkg_nofetch pkg_postinst pkg_postrm pkg_preinst
					src_prepare pkg_prerm pkg_pretend pkg_setup src_test src_unpack"
				;;
		esac

		DEFINED_PHASES=
		for _f in $_valid_phases ; do
			if declare -F $_f >/dev/null ; then
				_f=${_f#pkg_}
				DEFINED_PHASES+=" ${_f#src_}"
			fi
		done
		[[ -n $DEFINED_PHASES ]] || DEFINED_PHASES=-

		unset _f _valid_phases

		if [[ $EBUILD_PHASE != depend ]] ; then

			case "$EAPI" in
				0|1|2|3)
					_ebuild_helpers_path="$PORTAGE_BIN_PATH/ebuild-helpers"
					;;
				*)
					_ebuild_helpers_path="$PORTAGE_BIN_PATH/ebuild-helpers/4:$PORTAGE_BIN_PATH/ebuild-helpers"
					;;
			esac

			PATH=$_ebuild_helpers_path:$PREROOTPATH${PREROOTPATH:+:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin${ROOTPATH:+:}$ROOTPATH
			unset _ebuild_helpers_path

			if hasq distcc $FEATURES ; then
				PATH="/usr/lib/distcc/bin:$PATH"
				[[ -n $DISTCC_LOG ]] && addwrite "${DISTCC_LOG%/*}"
			fi

			if hasq ccache $FEATURES ; then
				PATH="/usr/lib/ccache/bin:$PATH"

				if [[ -n $CCACHE_DIR ]] ; then
					addread "$CCACHE_DIR"
					addwrite "$CCACHE_DIR"
				fi

				[[ -n $CCACHE_SIZE ]] && ccache -M $CCACHE_SIZE &> /dev/null
			fi

			if [[ -n $QA_PREBUILT ]] ; then

				# these ones support fnmatch patterns
				QA_EXECSTACK+=" $QA_PREBUILT"
				QA_TEXTRELS+=" $QA_PREBUILT"
				QA_WX_LOAD+=" $QA_PREBUILT"

				# these ones support regular expressions, so translate
				# fnmatch patterns to regular expressions
				for x in QA_DT_HASH QA_DT_NEEDED QA_PRESTRIPPED QA_SONAME ; do
					if [[ $(declare -p $x 2>/dev/null) = declare\ -a* ]] ; then
						eval "$x=(\"\${$x[@]}\" ${QA_PREBUILT//\*/.*})"
					else
						eval "$x+=\" ${QA_PREBUILT//\*/.*}\""
					fi
				done

				unset x
			fi

			# This needs to be exported since prepstrip is a separate shell script.
			[[ -n $QA_PRESTRIPPED ]] && export QA_PRESTRIPPED
			eval "[[ -n \$QA_PRESTRIPPED_${ARCH/-/_} ]] && \
				export QA_PRESTRIPPED_${ARCH/-/_}"
		fi
	fi
fi

# unset USE_EXPAND variables that contain only the special "*" token
for x in ${USE_EXPAND} ; do
	[ "${!x}" == "*" ] && unset ${x}
done
unset x

if hasq nostrip ${FEATURES} ${RESTRICT} || hasq strip ${RESTRICT}
then
	export DEBUGBUILD=1
fi

#a reasonable default for $S
[[ -z ${S} ]] && export S=${WORKDIR}/${P}

# Note: readonly variables interfere with preprocess_ebuild_env(), so
# declare them only after it has already run.
if [ "${EBUILD_PHASE}" != "depend" ] ; then
	declare -r $PORTAGE_READONLY_METADATA $PORTAGE_READONLY_VARS
	case "$EAPI" in
		0|1|2)
			;;
		*)
			declare -r ED EPREFIX EROOT
			;;
	esac
fi

ebuild_main() {

	# Subshell/helper die support (must export for the die helper).
	# Since this function is typically executed in a subshell,
	# setup EBUILD_MASTER_PID to refer to the current $BASHPID,
	# which seems to give the best results when further
	# nested subshells call die.
	export EBUILD_MASTER_PID=$BASHPID
	trap 'exit 1' SIGTERM

	if [[ $EBUILD_PHASE != depend ]] ; then
		# Force configure scripts that automatically detect ccache to
		# respect FEATURES="-ccache".
		hasq ccache $FEATURES || export CCACHE_DISABLE=1

		local phase_func=$(_ebuild_arg_to_phase "$EAPI" "$EBUILD_PHASE")
		[[ -n $phase_func ]] && _ebuild_phase_funcs "$EAPI" "$phase_func"
		unset phase_func
	fi

	source_all_bashrcs

	case ${EBUILD_SH_ARGS} in
	nofetch)
		ebuild_phase_with_hooks pkg_nofetch
		;;
	prerm|postrm|postinst|config|info)
		if hasq "$EBUILD_SH_ARGS" config info && \
			! declare -F "pkg_$EBUILD_SH_ARGS" >/dev/null ; then
			ewarn  "pkg_${EBUILD_SH_ARGS}() is not defined: '${EBUILD##*/}'"
		fi
		export SANDBOX_ON="0"
		if [ "${PORTAGE_DEBUG}" != "1" ] || [ "${-/x/}" != "$-" ]; then
			ebuild_phase_with_hooks pkg_${EBUILD_SH_ARGS}
		else
			set -x
			ebuild_phase_with_hooks pkg_${EBUILD_SH_ARGS}
			set +x
		fi
		if [[ $EBUILD_PHASE == postinst ]] && [[ -n $PORTAGE_UPDATE_ENV ]]; then
			# Update environment.bz2 in case installation phases
			# need to pass some variables to uninstallation phases.
			save_ebuild_env --exclude-init-phases | \
				filter_readonly_variables --filter-path \
				--filter-sandbox --allow-extra-vars \
				| ${PORTAGE_BZIP2_COMMAND} -c -f9 > "$PORTAGE_UPDATE_ENV"
			assert "save_ebuild_env failed"
		fi
		;;
	unpack|prepare|configure|compile|test|clean|install)
		if [[ ${SANDBOX_DISABLED:-0} = 0 ]] ; then
			export SANDBOX_ON="1"
		else
			export SANDBOX_ON="0"
		fi

		case "$EBUILD_SH_ARGS" in
		configure|compile)

			local x
			for x in ASFLAGS CCACHE_DIR CCACHE_SIZE \
				CFLAGS CXXFLAGS LDFLAGS LIBCFLAGS LIBCXXFLAGS ; do
				[[ ${!x+set} = set ]] && export $x
			done
			unset x

			hasq distcc $FEATURES && [[ -n $DISTCC_DIR ]] && \
				[[ ${SANDBOX_WRITE/$DISTCC_DIR} = $SANDBOX_WRITE ]] && \
				addwrite "$DISTCC_DIR"

			x=LIBDIR_$ABI
			[ -z "$PKG_CONFIG_PATH" -a -n "$ABI" -a -n "${!x}" ] && \
				export PKG_CONFIG_PATH=/usr/${!x}/pkgconfig

			if hasq noauto $FEATURES && \
				[[ ! -f $PORTAGE_BUILDDIR/.unpacked ]] ; then
				echo
				echo "!!! We apparently haven't unpacked..." \
					"This is probably not what you"
				echo "!!! want to be doing... You are using" \
					"FEATURES=noauto so I'll assume"
				echo "!!! that you know what you are doing..." \
					"You have 5 seconds to abort..."
				echo

				local x
				for x in 1 2 3 4 5 6 7 8; do
					LC_ALL=C sleep 0.25
				done

				sleep 3
			fi

			cd "$PORTAGE_BUILDDIR"
			if [ ! -d build-info ] ; then
				mkdir build-info
				cp "$EBUILD" "build-info/$PF.ebuild"
			fi

			#our custom version of libtool uses $S and $D to fix
			#invalid paths in .la files
			export S D

			;;
		esac

		if [ "${PORTAGE_DEBUG}" != "1" ] || [ "${-/x/}" != "$-" ]; then
			dyn_${EBUILD_SH_ARGS}
		else
			set -x
			dyn_${EBUILD_SH_ARGS}
			set +x
		fi
		export SANDBOX_ON="0"
		;;
	help|pretend|setup|preinst)
		#pkg_setup needs to be out of the sandbox for tmp file creation;
		#for example, awking and piping a file in /tmp requires a temp file to be created
		#in /etc.  If pkg_setup is in the sandbox, both our lilo and apache ebuilds break.
		export SANDBOX_ON="0"
		if [ "${PORTAGE_DEBUG}" != "1" ] || [ "${-/x/}" != "$-" ]; then
			dyn_${EBUILD_SH_ARGS}
		else
			set -x
			dyn_${EBUILD_SH_ARGS}
			set +x
		fi
		;;
	depend)
		export SANDBOX_ON="0"
		set -f

		if [ -n "${dbkey}" ] ; then
			if [ ! -d "${dbkey%/*}" ]; then
				install -d -g ${PORTAGE_GID} -m2775 "${dbkey%/*}"
			fi
			# Make it group writable. 666&~002==664
			umask 002
		fi

		auxdbkeys="DEPEND RDEPEND SLOT SRC_URI RESTRICT HOMEPAGE LICENSE
			DESCRIPTION KEYWORDS INHERITED IUSE REQUIRED_USE PDEPEND PROVIDE EAPI
			PROPERTIES DEFINED_PHASES UNUSED_05 UNUSED_04
			UNUSED_03 UNUSED_02 UNUSED_01"

		#the extra $(echo) commands remove newlines
		[ -n "${EAPI}" ] || EAPI=0

		if [ -n "${dbkey}" ] ; then
			> "${dbkey}"
			for f in ${auxdbkeys} ; do
				echo $(echo ${!f}) >> "${dbkey}" || exit $?
			done
		else
			for f in ${auxdbkeys} ; do
				echo $(echo ${!f}) 1>&9 || exit $?
			done
			exec 9>&-
		fi
		set +f
		;;
	_internal_test)
		;;
	*)
		export SANDBOX_ON="1"
		echo "Unrecognized EBUILD_SH_ARGS: '${EBUILD_SH_ARGS}'"
		echo
		dyn_help
		exit 1
		;;
	esac
}

if [[ -s $SANDBOX_LOG ]] ; then
	# We use SANDBOX_LOG to check for sandbox violations,
	# so we ensure that there can't be a stale log to
	# interfere with our logic.
	x=
	if [[ -n SANDBOX_ON ]] ; then
		x=$SANDBOX_ON
		export SANDBOX_ON=0
	fi

	rm -f "$SANDBOX_LOG" || \
		die "failed to remove stale sandbox log: '$SANDBOX_LOG'"

	if [[ -n $x ]] ; then
		export SANDBOX_ON=$x
	fi
	unset x
fi

if [[ $EBUILD_PHASE = depend ]] ; then
	ebuild_main
elif [[ -n $EBUILD_SH_ARGS ]] ; then
	(
		# Don't allow subprocesses to inherit the pipe which
		# emerge uses to monitor ebuild.sh.
		exec 9>&-

		ebuild_main

		# Save the env only for relevant phases.
		if ! hasq "$EBUILD_SH_ARGS" clean help info nofetch ; then
			umask 002
			save_ebuild_env | filter_readonly_variables \
				--filter-features > "$T/environment"
			assert "save_ebuild_env failed"
			chown portage:portage "$T/environment" &>/dev/null
			chmod g+w "$T/environment" &>/dev/null
		fi
		[[ -n $PORTAGE_EBUILD_EXIT_FILE ]] && > "$PORTAGE_EBUILD_EXIT_FILE"
		if [[ -n $PORTAGE_IPC_DAEMON ]] ; then
			[[ ! -s $SANDBOX_LOG ]]
			"$PORTAGE_BIN_PATH"/ebuild-ipc exit $?
		fi
		exit 0
	)
	exit $?
fi

# Do not exit when ebuild.sh is sourced by other scripts.
true
