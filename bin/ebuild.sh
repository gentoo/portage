#!/bin/bash
# Copyright 1999-2005 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/bin/ebuild.sh,v 1.201.2.42 2005/08/20 17:24:30 jstubbs Exp $

export SANDBOX_PREDICT="${SANDBOX_PREDICT}:/proc/self/maps:/dev/console:/usr/lib/portage/pym:/dev/random"
export SANDBOX_WRITE="${SANDBOX_WRITE}:/dev/shm:/dev/stdout:/dev/stderr:${PORTAGE_TMPDIR}"
export SANDBOX_READ="${SANDBOX_READ}:/dev/shm:/dev/stdin:${PORTAGE_TMPDIR}"

if [ ! -z "${PORTAGE_GPG_DIR}" ]; then
	SANDBOX_PREDICT="${SANDBOX_PREDICT}:${PORTAGE_GPG_DIR}"
fi

if [ "$*" != "depend" ] && [ "$*" != "clean" ] && [ "$*" != "nofetch" ]; then
	if [ -f "${T}/environment" ]; then
		source "${T}/environment" &>/dev/null
	fi
fi

if [ -n "$#" ]; then
	ARGS="${*}"
fi

declare -rx EBUILD_PHASE="$*"

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# Unset some variables that break things.
unset GZIP BZIP BZIP2 CDPATH GREP_OPTIONS GREP_COLOR GLOBIGNORE

# We need this next line for "die" and "assert". It expands
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases
alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
alias assert='_pipestatus="${PIPESTATUS[*]}"; [[ "${_pipestatus// /}" -eq 0 ]] || diefunc "$FUNCNAME" "$LINENO" "$_pipestatus"'
alias save_IFS='[ "${IFS:-unset}" != "unset" ] && old_IFS="${IFS}"'
alias restore_IFS='if [ "${old_IFS:-unset}" != "unset" ]; then IFS="${old_IFS}"; unset old_IFS; else unset IFS; fi'

OCC="$CC"
OCXX="$CXX"
source /etc/profile.env &>/dev/null
if [ -f "${PORTAGE_BASHRC}" ]; then
	source "${PORTAGE_BASHRC}"
fi
[ ! -z "$OCC" ] && export CC="$OCC"
[ ! -z "$OCXX" ] && export CXX="$OCXX"

export PATH="/sbin:/usr/sbin:/usr/lib/portage/bin:/bin:/usr/bin:${ROOTPATH}"
[ ! -z "$PREROOTPATH" ] && export PATH="${PREROOTPATH%%:}:$PATH"

source /usr/lib/portage/bin/isolated-functions.sh  &>/dev/null
# TODO: make this conditional on config settings, fix any remaining stuff
set_colors

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON="0"

# sandbox support functions; defined prior to profile.bashrc srcing, since the profile might need to add a default exception (/usr/lib64/conftest fex, bug #60147)
addread() {
	export SANDBOX_READ="$SANDBOX_READ:$1"
}

addwrite() {
	export SANDBOX_WRITE="$SANDBOX_WRITE:$1"
}

adddeny() {
	export SANDBOX_DENY="$SANDBOX_DENY:$1"
}

addpredict() {
	export SANDBOX_PREDICT="$SANDBOX_PREDICT:$1"
}

lchown() {
	chown -h "$@"
}

lchgrp() {
	chgrp -h "$@"
}

# source the existing profile.bashrc's.
save_IFS
IFS=$'\n'
for dir in ${PROFILE_PATHS}; do
	# Must unset it so that it doesn't mess up assumptions in the RCs.
	unset IFS
	if [ -f "${dir}/profile.bashrc" ]; then
		source "${dir}/profile.bashrc"
	fi
done
restore_IFS


esyslog() {
	# Custom version of esyslog() to take care of the "Red Star" bug.
	# MUST follow functions.sh to override the "" parameter problem.
	return 0
}


use() {
	if useq ${1}; then
		return 0
	fi
	return 1
}

usev() {
	if useq ${1}; then
		echo "${1}"
		return 0
	fi
	return 1
}

useq() {
	local u="${1}"
	local neg=0
	if [ "${u:0:1}" == "!" ]; then
		u="${u:1}"
		neg=1
	fi
	local x

	# Make sure we have this USE flag in IUSE
	if ! hasq "${u}" ${IUSE} ${E_IUSE} && ! hasq "${u}" ${PORTAGE_ARCHLIST} selinux; then
		echo "QA Notice: USE Flag '${u}' not in IUSE for ${CATEGORY}/${PF}" >&2
	fi

	for x in ${USE}; do
		if [ "${x}" == "${u}" ]; then
			if [ ${neg} -eq 1 ]; then
				return 1
			else
				return 0
			fi
		fi
	done
	if [ ${neg} -eq 1 ]; then
		return 0
	else
		return 1
	fi
}

has() {
	if hasq "$@"; then
		return 0
	fi
	return 1
}

hasv() {
	if hasq "$@"; then
		echo "${1}"
		return 0
	fi
	return 1
}

hasq() {
	local x

	local me=$1
	shift

	# All the TTY checks really only help out depend. Which is nice.
	# Logging kills all this anyway. Everything becomes a pipe. --NJ
	for x in "$@"; do
		if [ "${x}" == "${me}" ]; then
			return 0
		fi
	done
	return 1
}

has_version() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls (has_version calls portageq) are not allowed in the global scope"
	fi
	# return shell-true/shell-false if exists.
	# Takes single depend-type atoms.
	if /usr/lib/portage/bin/portageq 'has_version' "${ROOT}" "$1"; then
		return 0
	else
		return 1
	fi
}

portageq() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls are not allowed in the global scope"
	fi
	/usr/lib/portage/bin/portageq "$@"
}


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------


best_version() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls (best_version calls portageq) are not allowed in the global scope"
	fi
	# returns the best/most-current match.
	# Takes single depend-type atoms.
	/usr/lib/portage/bin/portageq 'best_version' "${ROOT}" "$1"
}

use_with() {
	if [ -z "$1" ]; then
		echo "!!! use_with() called without a parameter." >&2
		echo "!!! use_with <USEFLAG> [<flagname> [value]]" >&2
		return 1
	fi

	local UW_SUFFIX=""
	if [ ! -z "${3}" ]; then
		UW_SUFFIX="=${3}"
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi

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

	local UE_SUFFIX=""
	if [ ! -z "${3}" ]; then
		UE_SUFFIX="=${3}"
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi

	if useq $1; then
		echo "--enable-${UWORD}${UE_SUFFIX}"
	else
		echo "--disable-${UWORD}"
	fi
	return 0
}

register_die_hook() {
	export EBUILD_DEATH_HOOKS="${EBUILD_DEATH_HOOKS} $*"
}

diefunc() {
	local funcname="$1" lineno="$2" exitcode="$3"
	shift 3
	echo >&2
	echo "!!! ERROR: $CATEGORY/$PF failed." >&2
	echo "!!! Function $funcname, Line $lineno, Exitcode $exitcode" >&2
	echo "!!! ${*:-(no error message)}" >&2
	echo "!!! If you need support, post the topmost build error, NOT this status message." >&2
	echo >&2
	if [ "${EBUILD_PHASE/depend}" == "${EBUILD_PHASE}" ]; then
		for x in $EBUILD_DEATH_HOOKS; do
			${x} "$@" >&2 1>&2
		done
	fi
	exit 1
}

#if no perms are specified, dirs/files will have decent defaults
#(not secretive, but not stupid)
umask 022
export DESTTREE=/usr
export INSDESTTREE=""
export EXEDESTTREE=""
export DOCDESTTREE=""
export INSOPTIONS="-m0644"
export EXEOPTIONS="-m0755"
export LIBOPTIONS="-m0644"
export DIROPTIONS="-m0755"
export MOPREFIX=${PN}

check_KV() {
	if [ -z "${KV}" ]; then
		eerror ""
		eerror "Could not determine your kernel version."
		eerror "Make sure that you have /usr/src/linux symlink."
		eerror "And that said kernel has been configured."
		eerror "You can also simply run the following command"
		eerror "in the kernel referenced by /usr/src/linux:"
		eerror " make include/linux/version.h"
		eerror ""
		die
	fi
}

# adds ".keep" files so that dirs aren't auto-cleaned
keepdir() {
	dodir "$@"
	local x
	if [ "$1" == "-R" ] || [ "$1" == "-r" ]; then
		shift
		find "$@" -type d -printf "${D}/%p/.keep\n" | tr "\n" "\0" | $XARGS -0 -n100 touch || die "Failed to recursive create .keep files"
	else
		for x in "$@"; do
			touch "${D}/${x}/.keep" || die "Failed to create .keep in ${D}/${x}"
		done
	fi
}

unpack() {
	local x
	local y
	local myfail
	local tarvars

	if [ "$USERLAND" == "BSD" ]; then
		tarvars=""
	else
		tarvars="--no-same-owner"
	fi

	[ -z "$*" ] && die "Nothing passed to the 'unpack' command"

	for x in "$@"; do
		echo ">>> Unpacking ${x} to ${PWD}"
		y=${x%.*}
		y=${y##*.}

		myfail="${x} does not exist"
		if [ "${x:0:2}" = "./" ] ; then
			srcdir=""
		else
			srcdir="${DISTDIR}/"
		fi
		[ ! -s "${srcdir}${x}" ] && die "$myfail"

		myfail="failure unpacking ${x}"
		case "${x##*.}" in
			tar)
				tar xf "${srcdir}${x}" ${tarvars} || die "$myfail"
				;;
			tgz)
				tar xzf "${srcdir}${x}" ${tarvars} || die "$myfail"
				;;
			tbz2)
				bzip2 -dc "${srcdir}${x}" | tar xf - ${tarvars}
				assert "$myfail"
				;;
			ZIP|zip|jar)
				unzip -qo "${srcdir}${x}" || die "$myfail"
				;;
			gz|Z|z)
				if [ "${y}" == "tar" ]; then
					tar zxf "${srcdir}${x}" ${tarvars} || die "$myfail"
				else
					gzip -dc "${srcdir}${x}" > ${x%.*} || die "$myfail"
				fi
				;;
			bz2)
				if [ "${y}" == "tar" ]; then
					bzip2 -dc "${srcdir}${x}" | tar xf - ${tarvars}
					assert "$myfail"
				else
					bzip2 -dc "${srcdir}${x}" > ${x%.*} || die "$myfail"
				fi
				;;
			RAR|rar)
				unrar x -idq "${srcdir}/${x}" || die "$myfail"
				;;
			LHa|LHA|lha|lzh)
				lha xqf "${srcdir}/${x}" || die "$myfail"
				;;
			*)
				echo "unpack ${x}: file format not recognized. Ignoring."
				;;
		esac
	done
}

strip_duplicate_slashes () {
	if [ -n "${1}" ]; then
		local removed="${1/\/\///}"
		[ "${removed}" != "${removed/\/\///}" ] && removed=$(strip_duplicate_slashes "${removed}")
		echo ${removed}
	fi
}

econf() {
	local LOCAL_EXTRA_ECONF="${EXTRA_ECONF}"

	if [ -z "${ECONF_SOURCE}" ]; then
		ECONF_SOURCE="."
	fi
	if [ -x "${ECONF_SOURCE}/configure" ]; then
		if [ -e /usr/share/gnuconfig/ ]; then
			local x
			for x in $(find "${WORKDIR}" -type f '(' -name config.guess -o -name config.sub ')') ; do
				echo " * econf: updating ${x/${WORKDIR}\/} with /usr/share/gnuconfig/${x##*/}"
				cp -f /usr/share/gnuconfig/${x##*/} ${x}
			done
		fi

		if [ ! -z "${CBUILD}" ]; then
			LOCAL_EXTRA_ECONF="--build=${CBUILD} ${LOCAL_EXTRA_ECONF}"
		fi

		if [ ! -z "${CTARGET}" ]; then
			LOCAL_EXTRA_ECONF="--target=${CTARGET} ${LOCAL_EXTRA_ECONF}"
		fi

		# if the profile defines a location to install libs to aside from default, pass it on.
		# if the ebuild passes in --libdir, they're responsible for the conf_libdir fun.
		LIBDIR_VAR="LIBDIR_${ABI}"
		if [ -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
			CONF_LIBDIR="${!LIBDIR_VAR}"
		fi
		unset LIBDIR_VAR
		if [ -n "${CONF_LIBDIR}" ] && [ "${*/--libdir}" == "$*" ]; then
			if [ "${*/--exec-prefix}" != "$*" ]; then
				local args="$(echo $*)"
				local -a pref=($(echo ${args/*--exec-prefix[= ]}))
				CONF_PREFIX=${pref}
				[ "${CONF_PREFIX:0:1}" != "/" ] && CONF_PREFIX="/${CONF_PREFIX}"
			elif [ "${*/--prefix}" != "$*" ]; then
				local args="$(echo $*)"
				local -a pref=($(echo ${args/*--prefix[= ]}))
				CONF_PREFIX=${pref}
				[ "${CONF_PREFIX:0:1}" != "/" ] && CONF_PREFIX="/${CONF_PREFIX}"
			else
				CONF_PREFIX="/usr"
			fi
			export CONF_PREFIX
			[ "${CONF_LIBDIR:0:1}" != "/" ] && CONF_LIBDIR="/${CONF_LIBDIR}"

			CONF_LIBDIR_RESULT="${CONF_PREFIX}${CONF_LIBDIR}"
			for X in 1 2 3; do
				# The escaping is weird. It will break if you escape the last one.
				CONF_LIBDIR_RESULT="${CONF_LIBDIR_RESULT//\/\///}"
			done

			LOCAL_EXTRA_ECONF="--libdir=${CONF_LIBDIR_RESULT} ${LOCAL_EXTRA_ECONF}"
		fi

		echo "${ECONF_SOURCE}/configure" \
			--prefix=/usr \
			--host=${CHOST} \
			--mandir=/usr/share/man \
			--infodir=/usr/share/info \
			--datadir=/usr/share \
			--sysconfdir=/etc \
			--localstatedir=/var/lib \
			"$@" \
			${LOCAL_EXTRA_ECONF}

		if ! "${ECONF_SOURCE}/configure" \
			--prefix=/usr \
			--host=${CHOST} \
			--mandir=/usr/share/man \
			--infodir=/usr/share/info \
			--datadir=/usr/share \
			--sysconfdir=/etc \
			--localstatedir=/var/lib \
			"$@"  \
			${LOCAL_EXTRA_ECONF}; then

			if [ -s config.log ]; then
				echo
				echo "!!! Please attach the following file when filing a report to bugs.gentoo.org:"
				echo "!!! ${PWD}/config.log"
			fi
			die "econf failed"
		fi
	else
		die "no configure script found"
	fi
}

einstall() {
	# CONF_PREFIX is only set if they didn't pass in libdir above.
	LIBDIR_VAR="LIBDIR_${ABI}"
	if [ -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
		CONF_LIBDIR="${!LIBDIR_VAR}"
	fi
	unset LIBDIR_VAR
	if [ -n "${CONF_LIBDIR}" ] && [ "${CONF_PREFIX:-unset}" != "unset" ]; then
		EI_DESTLIBDIR="${D}/${CONF_PREFIX}/${CONF_LIBDIR}"
		EI_DESTLIBDIR="$(strip_duplicate_slashes ${EI_DESTLIBDIR})"
		EXTRA_EINSTALL="libdir=${EI_DESTLIBDIR} ${EXTRA_EINSTALL}"
		unset EI_DESTLIBDIR
	fi

	if [ -f ./[mM]akefile -o -f ./GNUmakefile ] ; then
		if [ ! -z "${PORTAGE_DEBUG}" ]; then
			make -n prefix=${D}/usr \
				datadir=${D}/usr/share \
				infodir=${D}/usr/share/info \
				localstatedir=${D}/var/lib \
				mandir=${D}/usr/share/man \
				sysconfdir=${D}/etc \
				${EXTRA_EINSTALL} \
				"$@" install
		fi
		make prefix=${D}/usr \
			datadir=${D}/usr/share \
			infodir=${D}/usr/share/info \
			localstatedir=${D}/var/lib \
			mandir=${D}/usr/share/man \
			sysconfdir=${D}/etc \
			${EXTRA_EINSTALL} \
			"$@" install || die "einstall failed"
	else
		die "no Makefile found"
	fi
}

pkg_setup() {
	return
}

pkg_nofetch() {
	[ -z "${SRC_URI}" ] && return

	echo "!!! The following are listed in SRC_URI for ${PN}:"
	for MYFILE in `echo ${SRC_URI}`; do
		echo "!!!   $MYFILE"
	done
}

src_unpack() {
	if [ "${A}" != "" ]; then
		unpack ${A}
	fi
}

src_compile() {
	if [ -x ./configure ]; then
		econf
	fi
	if [ -f Makefile ] || [ -f GNUmakefile ] || [ -f makefile ]; then
		emake || die "emake failed"
	fi
}

src_test() {
	addpredict /
	if emake -j1 check -n &> /dev/null; then
		echo ">>> Test phase [check]: ${CATEGORY}/${PF}"
		if ! emake -j1 check; then
			hasq test $FEATURES && die "Make check failed. See above for details."
			hasq test $FEATURES || eerror "Make check failed. See above for details."
		fi
	elif emake -j1 test -n &> /dev/null; then
		echo ">>> Test phase [test]: ${CATEGORY}/${PF}"
		if ! emake -j1 test; then
			hasq test $FEATURES && die "Make test failed. See above for details."
			hasq test $FEATURES || eerror "Make test failed. See above for details."
		fi
	else
		echo ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
	SANDBOX_PREDICT="${SANDBOX_PREDICT%:/}"
}

src_install() {
	return
}

pkg_preinst() {
	return
}

pkg_postinst() {
	return
}

pkg_prerm() {
	return
}

pkg_postrm() {
	return
}

pkg_config() {
	eerror "This ebuild does not have a config function."
}

# Used to generate the /lib/cpp and /usr/bin/cc wrappers
gen_wrapper() {
	cat > $1 << END
#!/bin/sh

$2 "\$@"
END

	chmod 0755 $1
}

dyn_setup() {
	[ "$(type -t pre_pkg_setup)" == "function" ] && pre_pkg_setup
	pkg_setup
	[ "$(type -t post_pkg_setup)" == "function" ] && post_pkg_setup
}

dyn_unpack() {
	trap "abort_unpack" SIGINT SIGQUIT
	[ "$(type -t pre_src_unpack)" == "function" ] && pre_src_unpack
	local newstuff="no"
	if [ -e "${WORKDIR}" ]; then
		local x
		local checkme
		for x in ${AA}; do
			echo ">>> Checking ${x}'s mtime..."
			if [ "${DISTDIR}/${x}" -nt "${WORKDIR}" ]; then
				echo ">>> ${x} has been updated; recreating WORKDIR..."
				newstuff="yes"
				rm -rf "${WORKDIR}"
				break
			fi
		done
		if [ "${EBUILD}" -nt "${WORKDIR}" ]; then
			echo ">>> ${EBUILD} has been updated; recreating WORKDIR..."
			newstuff="yes"
			rm -rf "${WORKDIR}"
		elif [ ! -f "${PORTAGE_BUILDDIR}/.unpacked" ]; then
			echo ">>> Not marked as unpacked; recreating WORKDIR..."
			newstuff="yes"
			rm -rf "${WORKDIR}"
		fi
	fi
	if [ -e "${WORKDIR}" ]; then
		if [ "$newstuff" == "no" ]; then
			echo ">>> WORKDIR is up-to-date, keeping..."
			[ "$(type -t post_src_unpack)" == "function" ] && post_src_unpack
			return 0
		fi
	fi

	install -m0700 -d "${WORKDIR}" || die "Failed to create dir '${WORKDIR}'"
	[ -d "$WORKDIR" ] && cd "${WORKDIR}"
	echo ">>> Unpacking source..."
	src_unpack
	touch "${PORTAGE_BUILDDIR}/.unpacked" || die "IO Failure -- Failed 'touch .unpacked' in BUILDIR"
	echo ">>> Source unpacked."
	cd "${PORTAGE_BUILDDIR}"

	[ "$(type -t post_src_unpack)" == "function" ] && post_src_unpack

	trap SIGINT SIGQUIT
}

dyn_clean() {
	if [ "$USERLAND" == "BSD" ] && type -p chflags &>/dev/null; then
		chflags -R noschg,nouchg,nosappnd,nouappnd,nosunlnk,nouunlnk \
			"${PORTAGE_BUILDDIR}"
	fi

	if [ "$USERLAND" == "Darwin" ] && type -p chflags &>/dev/null; then
		chflags -R noschg,nouchg,nosappnd,nouappnd "${PORTAGE_BUILDDIR}"
	fi

	rm -rf "${PORTAGE_BUILDDIR}/image"

	if ! hasq keeptemp $FEATURES; then
		rm -rf "${T}"
	else
		mv "${T}/environment" "${T}/environment.keeptemp"
	fi

	if ! hasq keepwork $FEATURES; then
		rm -rf "${PORTAGE_BUILDDIR}/.unpacked"
		rm -rf "${PORTAGE_BUILDDIR}/.compiled"
		rm -rf "${PORTAGE_BUILDDIR}/.tested"
		rm -rf "${PORTAGE_BUILDDIR}/.installed"
		rm -rf "${PORTAGE_BUILDDIR}/.packaged"
		rm -rf "${PORTAGE_BUILDDIR}/build-info"
		rm -rf "${WORKDIR}"
	fi

	if [ -f "${PORTAGE_BUILDDIR}/.unpacked" ]; then
		find "${PORTAGE_BUILDDIR}" -type d ! -regex "^${WORKDIR}" | sort -r | tr "\n" "\0" | $XARGS -0 rmdir &>/dev/null
	fi

	if [ -z "$(find "${PORTAGE_BUILDDIR}" -mindepth 1 -maxdepth 1)" ]; then
		rmdir "${PORTAGE_BUILDDIR}"
	fi
	# do not bind this to doebuild defined DISTDIR; don't trust doebuild, and if mistakes are made it'll
	# result in it wiping the users distfiles directory (bad).
	rm -rf "${PORTAGE_BUILDDIR}/distdir"
	true
}

into() {
	if [ "$1" == "/" ]; then
		export DESTTREE=""
	else
		export DESTTREE=$1
		if [ ! -d "${D}${DESTTREE}" ]; then
			install -d "${D}${DESTTREE}"
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
		fi
	fi
}

exeinto() {
	if [ "$1" == "/" ]; then
		export EXEDESTTREE=""
	else
		export EXEDESTTREE="$1"
		if [ ! -d "${D}${EXEDESTTREE}" ]; then
			install -d "${D}${EXEDESTTREE}"
		fi
	fi
}

docinto() {
	if [ "$1" == "/" ]; then
		export DOCDESTTREE=""
	else
		export DOCDESTTREE="$1"
		if [ ! -d "${D}usr/share/doc/${PF}/${DOCDESTTREE}" ]; then
			install -d "${D}usr/share/doc/${PF}/${DOCDESTTREE}"
		fi
	fi
}

insopts() {
	INSOPTIONS=""
	for x in $*; do
		#if we have a debug build, let's not strip anything
		if hasq nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
			continue
		else
			INSOPTIONS="$INSOPTIONS $x"
		fi
	done
	export INSOPTIONS
}

diropts() {
	DIROPTIONS=""
	for x in $*; do
		DIROPTIONS="${DIROPTIONS} $x"
	done
	export DIROPTIONS
}

exeopts() {
	EXEOPTIONS=""
	for x in $*; do
		#if we have a debug build, let's not strip anything
		if hasq nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
			continue
		else
			EXEOPTIONS="$EXEOPTIONS $x"
		fi
	done
	export EXEOPTIONS
}

libopts() {
	LIBOPTIONS=""
	for x in $*; do
		#if we have a debug build, let's not strip anything
		if hasq nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
			continue
		else
			LIBOPTIONS="$LIBOPTIONS $x"
		fi
	done
	export LIBOPTIONS
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
	trap SIGINT SIGQUIT
}

abort_compile() {
	abort_handler "src_compile" $1
	rm -f "${PORTAGE_BUILDDIR}/.compiled"
	exit 1
}

abort_unpack() {
	abort_handler "src_unpack" $1
	rm -f "${PORTAGE_BUILDDIR}/.unpacked"
	rm -rf "${PORTAGE_BUILDDIR}/work"
	exit 1
}

abort_package() {
	abort_handler "dyn_package" $1
	rm -f "${PORTAGE_BUILDDIR}/.packaged"
	rm -f "${PKGDIR}"/All/${PF}.t*
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

dyn_compile() {
	trap "abort_compile" SIGINT SIGQUIT

	[ "$(type -t pre_src_compile)" == "function" ] && pre_src_compile

	[ "${CFLAGS-unset}"      != "unset" ] && export CFLAGS
	[ "${CXXFLAGS-unset}"    != "unset" ] && export CXXFLAGS
	[ "${LIBCFLAGS-unset}"   != "unset" ] && export LIBCFLAGS
	[ "${LIBCXXFLAGS-unset}" != "unset" ] && export LIBCXXFLAGS
	[ "${LDFLAGS-unset}"     != "unset" ] && export LDFLAGS
	[ "${ASFLAGS-unset}"     != "unset" ] && export ASFLAGS

	[ "${CCACHE_DIR-unset}"  != "unset" ] && export CCACHE_DIR
	[ "${CCACHE_SIZE-unset}" != "unset" ] && export CCACHE_SIZE

	[ "${DISTCC_DIR-unset}"  == "unset" ] && export DISTCC_DIR="${PORTAGE_TMPDIR}/.distcc"
	[ ! -z "${DISTCC_DIR}" ] && addwrite "${DISTCC_DIR}"

	if hasq noauto $FEATURES &>/dev/null && [ ! -f ${PORTAGE_BUILDDIR}/.unpacked ]; then
		echo
		echo "!!! We apparently haven't unpacked... This is probably not what you"
		echo "!!! want to be doing... You are using FEATURES=noauto so I'll assume"
		echo "!!! that you know what you are doing... You have 5 seconds to abort..."
		echo

		for x in 1 2 3 4 5 6 7 8; do
			echo -ne "\a"
			LC_ALL=C sleep 0.25
		done

		sleep 3
	fi

	local srcdir=${PORTAGE_BUILDDIR}
	cd "${PORTAGE_BUILDDIR}"
	if [ ! -e "build-info" ]; then
		mkdir build-info
	fi
	cp "${EBUILD}" "build-info/${PF}.ebuild"

	if [ "${PORTAGE_BUILDDIR}/.compiled" -nt "${WORKDIR}" ]; then
		echo ">>> It appears that ${PN} is already compiled; skipping."
		echo ">>> (clean to force compilation)"
		trap SIGINT SIGQUIT
		[ "$(type -t post_src_compile)" == "function" ] && post_src_compile
		return
	fi
	if [ -d "${S}" ]; then
		srcdir=${S}
		cd "${S}"
	fi
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages use an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"
	echo ">>> Compiling source in ${srcdir} ..."
	src_compile
	echo ">>> Source compiled."
	#|| abort_compile "fail"
	cd "${PORTAGE_BUILDDIR}"
	touch .compiled
	cd build-info

	for f in ASFLAGS CATEGORY CBUILD CC CFLAGS CHOST CXX \
		CXXFLAGS DEPEND EXTRA_ECONF EXTRA_EINSTALL EXTRA_MAKE \
		FEATURES INHERITED IUSE LDFLAGS LIBCFLAGS LIBCXXFLAGS \
		LICENSE PDEPEND PF PKGUSE PROVIDE RDEPEND RESTRICT SLOT; do
		[ -n "${!f}" ] && echo "${!f}" | tr '\n,\r,\t' ' , , ' | sed s/'  \+'/' '/g > ${f}
	done
	echo "${USE}"		> USE
	echo "${EAPI:-0}"	> EAPI
	set                     >  environment
	export -p | sed 's:declare -rx:declare -x:' >> environment
	bzip2 -9 environment

	cp "${EBUILD}" "${PF}.ebuild"
	if hasq nostrip $FEATURES $RESTRICT; then
		touch DEBUGBUILD
	fi

	[ "$(type -t post_src_compile)" == "function" ] && post_src_compile

	trap SIGINT SIGQUIT
}

dyn_package() {
	trap "abort_package" SIGINT SIGQUIT
	cd "${PORTAGE_BUILDDIR}/image"
	tar cpvf - ./ | bzip2 -f > ../bin.tar.bz2 || die "Failed to create tarball"
	cd ..
	xpak build-info inf.xpak
	tbz2tool join bin.tar.bz2 inf.xpak "${PF}.tbz2"
	mv "${PF}.tbz2" "${PKGDIR}/All" || die "Failed to move tbz2 to ${PKGDIR}/All"
	rm -f inf.xpak bin.tar.bz2
	if [ ! -d "${PKGDIR}/${CATEGORY}" ]; then
		install -d "${PKGDIR}/${CATEGORY}"
	fi
	ln -sf "../All/${PF}.tbz2" "${PKGDIR}/${CATEGORY}/${PF}.tbz2" || die "Failed to create symlink in ${PKGDIR}/${CATEGORY}"
	echo ">>> Done."
	cd "${PORTAGE_BUILDDIR}"
	touch .packaged || die "Failed to 'touch .packaged' in ${PORTAGE_BUILDDIR}"
	trap SIGINT SIGQUIT
}


dyn_test() {
	[ "$(type -t pre_src_test)" == "function" ] && pre_src_test
	if [ "${PORTAGE_BUILDDIR}/.tested" -nt "${WORKDIR}" ]; then
		echo ">>> It appears that ${PN} has already been tested; skipping."
		[ "$(type -t post_src_test)" == "function" ] && post_src_test
		return
	fi
	trap "abort_test" SIGINT SIGQUIT
	if [ -d "${S}" ]; then
		cd "${S}"
	fi
	if hasq test $RESTRICT; then
		ewarn "Skipping make test/check due to ebuild restriction."
		echo ">>> Test phase [explicitly disabled]: ${CATEGORY}/${PF}"
	elif ! hasq test $FEATURES; then
		echo ">>> Test phase [not enabled]: ${CATEGORY}/${PF}"
	else
		src_test
	fi

	cd "${PORTAGE_BUILDDIR}"
	touch .tested || die "Failed to 'touch .tested' in ${PORTAGE_BUILDDIR}"
	[ "$(type -t post_src_test)" == "function" ] && post_src_test
	trap SIGINT SIGQUIT
}


PORTAGE_INST_UID="0"
PORTAGE_INST_GID="0"

dyn_install() {
	trap "abort_install" SIGINT SIGQUIT
	[ "$(type -t pre_src_install)" == "function" ] && pre_src_install
	rm -rf "${PORTAGE_BUILDDIR}/image"
	mkdir "${PORTAGE_BUILDDIR}/image"
	if [ -d "${S}" ]; then
		cd "${S}"
	fi
	echo
	echo ">>> Install ${PF} into ${D} category ${CATEGORY}"
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages uses an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"
	src_install
	#|| abort_install "fail"
	prepall
	cd "${D}"

	declare -i UNSAFE=0
	for i in $(find "${D}/" -type f -perm -2002); do
		((UNSAFE++))
		echo "UNSAFE SetGID: $i"
		chmod -s,o-w "$i"
	done
	for i in $(find "${D}/" -type f -perm -4002); do
		((UNSAFE++))
		echo "UNSAFE SetUID: $i"
		chmod -s,o-w "$i"
	done

	# Now we look for all world writable files.
	for i in $(find "${D}/" -type f -perm -2); do
		echo -ne '\a'
		echo "QA Security Notice:"
		echo "- ${i:${#D}:${#i}} will be a world writable file."
		echo "- This may or may not be a security problem, most of the time it is one."
		echo "- Please double check that $PF really needs a world writeable bit and file bugs accordingly."
		sleep 1
	done

	if type -p scanelf > /dev/null ; then
		local insecure_rpath=0

		# Make sure we disallow insecure RUNPATH/RPATH's
		# Don't want paths that point to the tree where the package was built
		# (older, broken libtools would do this).  Also check for null paths
		# because the loader will search $PWD when it finds null paths.
		f=$(scanelf -qyRF '%r %p' "${D}" | grep -E "(${PORTAGE_BUILDDIR}|: |::|^ )")
		if [[ -n ${f} ]] ; then
			echo -ne '\a\n'
			echo "QA Notice: the following files contain insecure RUNPATH's"
			echo " Please file a bug about this at http://bugs.gentoo.org/"
			echo " For more information on this issue, kindly review:"
			echo " http://bugs.gentoo.org/81745"
			echo "${f}"
			echo -ne '\a\n'
			insecure_rpath=1
		fi

		# Check for setid binaries but are not built with BIND_NOW
		f=$(scanelf -qyRF '%b %p' "${D}")
		if [[ -n ${f} ]] ; then
			echo -ne '\a\n'
			echo "QA Notice: the following files are setXid, dyn linked, and using lazy bindings"
			echo " This combination is generally discouraged.  Try re-emerging the package:"
			echo " LDFLAGS='-Wl,-z,now' emerge ${PN}"
			echo "${f}"
			echo -ne '\a\n'
			die_msg="${die_msg} setXid lazy bindings,"
			sleep 1
		fi

		# TEXTREL's are baaaaaaaad
		f=$(scanelf -qyRF '%t %p' "${D}")
		if [[ -n ${f} ]] ; then
			echo -ne '\a\n'
			echo "QA Notice: the following files contain runtime text relocations"
			echo " Text relocations force the dynamic linker to perform extra"
			echo " work at startup, waste system resources, and may pose a security"
			echo " risk.  On some architectures, the code may not even function"
			echo " properly, if at all."
			echo "${f}"
			echo -ne '\a\n'
			die_msg="${die_msg} textrels,"
			sleep 1
		fi

		# Check for files with executable stacks
		f=$(scanelf -qyRF '%e %p' "${D}")
		if [[ -n ${f} ]] ; then
			echo -ne '\a\n'
			echo "QA Notice: the following files contain executable stacks"
			echo " Files with executable stacks will not work properly (or at all!)"
			echo " on some architectures/operating systems.  A bug should be filed"
			echo " at http://bugs.gentoo.org/ to make sure the file is fixed."
			echo "${f}"
			echo -ne '\a\n'
			die_msg="${die_msg} execstacks"
			sleep 1
		fi

		# Save NEEDED information
		scanelf -qyRF '%p %n' "${D}" | sed -e 's:^:/:' > "${PORTAGE_BUILDDIR}"/build-info/NEEDED

		if [[ ${insecure_rpath} -eq 1 ]] ; then
			die "Aborting due to serious QA concerns with RUNPATH/RPATH"
		elif [[ ${die_msg} != "" ]] && has stricter ${FEATURES} && ! has stricter ${RESTRICT} ; then
			die "Aborting due to QA concerns: ${die_msg}"
		fi
	fi

	if [[ ${UNSAFE} > 0 ]] ; then
		die "There are ${UNSAFE} unsafe files. Portage will not install them."
	fi

	# dumps perms to stdout.  if error, no perms dumped.
	function stat_perms() {
		local f
		# only define do_stat if it hasn't been already
		if ! type -p do_stat &> /dev/null; then
			if ! type -p stat &>/dev/null; then
				do_stat() {
					# Generic version -- Octal result
					python -c "import os,stat; print '%o' % os.stat('$1')[stat.ST_MODE]"
				}
			else
				if [ "${USERLAND}" == "BSD" ] || [ "${USERLAND}" == "Darwin" ]; then
					do_stat() {
						# BSD version -- Octal result
						$(type -p stat) -f '%p' "$1"
					}
				else
					do_stat() {
						# Linux version -- Hex result converted to Octal
						f=$($(type -p stat) -c '%f' "$1") || return $?
						printf '%o' "0x$f"
					}
				fi
			fi
		fi

		f=$(do_stat "$@") || return
		f="${f:2:4}"
		echo $f
	}

	local file s
	local count=0
	find "${D}/" -user  portage | while read file; do
		count=$(( $count + 1 ))
		if [ -L "${file}" ]; then
			lchown ${PORTAGE_INST_UID} "${file}"
		else
			s=$(stat_perms "$file")
			if [ -z "${s}" ]; then
				ewarn "failed stat_perm'ing $file.  User intervention during install isn't wise..."
				continue
			fi
			chown ${PORTAGE_INST_UID} "$file"
			chmod "$s" "$file"
		fi
	done
	if (( $count > 0 )); then
		ewarn "$count files were installed with user portage!"
	fi

	count=0
	find "${D}/" -group portage | while read file; do
		count=$(( $count + 1 ))
		if [ -L "${file}" ]; then
			lchgrp ${PORTAGE_INST_GID} "${file}"
		else
			s=$(stat_perms "$file")
			if [ -z "${s}" ]; then
				echo "failed stat_perm'ing '$file' . User intervention during install isn't wise..."
				continue
			fi
			chgrp ${PORTAGE_INST_GID} "$file"
			chmod "$s" "$file"
		fi
	done
	if (( $count > 0 )); then
		ewarn "$count files were installed with group portage!"
	fi

	unset -f stat_perms

	# Portage regenerates this on the installed system.
	if [ -f "${D}/usr/share/info/dir.gz" ]; then
		rm -f "${D}/usr/share/info/dir.gz"
	fi

	if hasq multilib-strict ${FEATURES} && [ -x /usr/bin/file -a -x /usr/bin/find -a \
	     -n "${MULTILIB_STRICT_DIRS}" -a -n "${MULTILIB_STRICT_DENY}" ]; then
		MULTILIB_STRICT_EXEMPT=${MULTILIB_STRICT_EXEMPT:-"(perl5|gcc|gcc-lib|debug)"}
		for dir in ${MULTILIB_STRICT_DIRS}; do
			[ -d "${D}/${dir}" ] || continue
			for file in $(find ${D}/${dir} -type f | egrep -v "^${D}/${dir}/${MULTILIB_STRICT_EXEMPT}"); do
				file ${file} | egrep -q "${MULTILIB_STRICT_DENY}" && die "File ${file} matches a file type that is not allowed in ${dir}"
			done
		done
	fi

	touch "${PORTAGE_BUILDDIR}/.installed"
	echo ">>> Completed installing ${PF} into ${D}"
	echo
	cd ${PORTAGE_BUILDDIR}
	[ "$(type -t post_src_install)" == "function" ] && post_src_install
	trap SIGINT SIGQUIT
}

dyn_preinst() {
	# set IMAGE depending if this is a binary or compile merge
	[ "${EMERGE_FROM}" == "binary" ] && IMAGE=${PKG_TMPDIR}/${PF}/bin \
					|| IMAGE=${D}

	[ "$(type -t pre_pkg_preinst)" == "function" ] && pre_pkg_preinst

	declare -r D=${IMAGE}
	pkg_preinst

	# remove man pages, info pages, docs if requested
	for f in man info doc; do
		if hasq no${f} $FEATURES; then
			INSTALL_MASK="${INSTALL_MASK} /usr/share/${f}"
		fi
	done

	# we don't want globbing for initial expansion, but afterwards, we do
	local shopts=$-
	set -o noglob
	for no_inst in ${INSTALL_MASK}; do
		set +o noglob
		einfo "Removing ${no_inst}"
		# normal stuff
		rm -Rf ${IMAGE}/${no_inst} >&/dev/null

		# we also need to handle globs (*.a, *.h, etc)
		find "${IMAGE}" -name ${no_inst} -exec rm -fR {} \; >&/dev/null
	done
	# set everything back the way we found it
	set +o noglob
	set -${shopts}

	# remove share dir if unnessesary
	if hasq nodoc $FEATURES -o hasq noman $FEATURES -o hasq noinfo $FEATURES; then
		rmdir "${IMAGE}/usr/share" &> /dev/null
	fi

	# Smart FileSystem Permissions
	if hasq sfperms $FEATURES; then
		for i in $(find ${IMAGE}/ -type f -perm -4000); do
			ebegin ">>> SetUID: [chmod go-r] $i "
			chmod go-r "$i"
			eend $?
		done
		for i in $(find ${IMAGE}/ -type f -perm -2000); do
			ebegin ">>> SetGID: [chmod o-r] $i "
			chmod o-r "$i"
			eend $?
		done
	fi

	# total suid control.
	if hasq suidctl $FEATURES > /dev/null ; then
		sfconf=/etc/portage/suidctl.conf
		echo ">>> Preforming suid scan in ${IMAGE}"
		for i in $(find ${IMAGE}/ -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [ -s "${sfconf}" ]; then
				suid="`grep ^${i/${IMAGE}/}$ ${sfconf}`"
				if [ "${suid}" = "${i/${IMAGE}/}" ]; then
					echo "- ${i/${IMAGE}/} is an approved suid file"
				else
					echo ">>> Removing sbit on non registered ${i/${IMAGE}/}"
					for x in 5 4 3 2 1 0; do echo -ne "\a"; sleep 0.25 ; done
					echo -ne "\a"
					chmod ugo-s "${i}"
					grep ^#${i/${IMAGE}/}$ ${sfconf} > /dev/null || {
						# sandbox prevents us from writing directly
						# to files outside of the sandbox, but this
						# can easly be bypassed using the addwrite() function
						addwrite "${sfconf}"
						echo ">>> Appending commented out entry to ${sfconf} for ${PF}"
						ls_ret=`ls -ldh "${i}"`
						echo "## ${ls_ret%${IMAGE}*}${ls_ret#*${IMAGE}}" >> ${sfconf}
						echo "#${i/${IMAGE}/}" >> ${sfconf}
						# no delwrite() eh?
						# delwrite ${sconf}
					}
				fi
			else
				echo "suidctl feature set but you are lacking a ${sfconf}"
			fi
		done
	fi

	# SELinux file labeling (needs to always be last in dyn_preinst)
	if useq selinux; then
		# only attempt to label if setfiles is executable
		# and 'context' is available on selinuxfs.
		if [ -f /selinux/context -a -x /usr/sbin/setfiles ]; then
			echo ">>> Setting SELinux security labels"
			if [ -f ${POLICYDIR}/file_contexts/file_contexts ]; then
				cp -f "${POLICYDIR}/file_contexts/file_contexts" "${T}"
			else
				make -C "${POLICYDIR}" FC=${T}/file_contexts "${T}/file_contexts"
			fi

			addwrite /selinux/context
			/usr/sbin/setfiles -r "${IMAGE}" "${T}/file_contexts" "${IMAGE}" \
				|| die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			echo "!!! Unable to set SELinux security labels"
		fi
	fi

	[ "$(type -t post_pkg_preinst)" == "function" ] && post_pkg_preinst

	trap SIGINT SIGQUIT
}

dyn_spec() {
	tar czf "/usr/src/redhat/SOURCES/${PF}.tar.gz" "${O}/${PF}.ebuild" "${O}/files" || die "Failed to create base rpm tarball."

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
	dyn_spec
	rpmbuild -bb "${PF}.spec" || die "Failed to integrate rpm spec file"
	install -D "/usr/src/redhat/RPMS/i386/${PN}-${PV}-${PR}.i386.rpm" "${RPMDIR}/${CATEGORY}/${PN}-${PV}-${PR}.rpm" || die "Failed to move rpm"
}

dyn_help() {
	echo
	echo "Portage"
	echo "Copyright 1999-2004 Gentoo Foundation"
	echo
	echo "How to use the ebuild command:"
	echo
	echo "The first argument to ebuild should be an existing .ebuild file."
	echo
	echo "One or more of the following options can then be specified.  If more"
	echo "than one option is specified, each will be executed in order."
	echo
	echo "  help        : show this help screen"
	echo "  setup       : execute package specific setup actions"
	echo "  fetch       : download source archive(s) and patches"
	echo "  digest      : creates a digest and a manifest file for the package"
	echo "  manifest    : creates a manifest file for the package"
	echo "  unpack      : unpack/patch sources (auto-fetch if needed)"
	echo "  compile     : compile sources (auto-fetch/unpack if needed)"
	echo "  test        : test package (auto-fetch/unpack/compile if needed)"
	echo "  preinst     : execute pre-install instructions"
	echo "  postinst    : execute post-install instructions"
	echo "  install     : installs the package to the temporary install directory"
	echo "  qmerge      : merge image into live filesystem, recording files in db"
	echo "  merge       : does fetch, unpack, compile, install and qmerge"
	echo "  prerm       : execute pre-removal instructions"
	echo "  postrm      : execute post-removal instructions"
	echo "  unmerge     : remove package from live filesystem"
	echo "  config      : execute package specific configuration actions"
	echo "  package     : create tarball package in ${PKGDIR}/All"
	echo "  rpm         : builds a RedHat RPM package"
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
	if hasq nostrip $FEATURES $RESTRICT; then
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
	[ -z "$T" ] && return 0

	while [ "$1" ]; do

		# extra user-configurable targets
		if [ "$ECLASS_DEBUG_OUTPUT" == "on" ]; then
			echo "debug: $1"
		elif [ -n "$ECLASS_DEBUG_OUTPUT" ]; then
			echo "debug: $1" >> $ECLASS_DEBUG_OUTPUT
		fi

		# default target
		echo "$1" >> "${T}/eclass-debug.log"
		# let the portage user own/write to this file
		chmod g+w "${T}/eclass-debug.log" &>/dev/null

		shift
	done
}

# The following 2 functions are debug-print() wrappers

debug-print-function() {
	str="$1: entering function"
	shift
	debug-print "$str, parameters: $*"
}

debug-print-section() {
	debug-print "now in section $*"
}

# Sources all eclasses in parameters
declare -ix ECLASS_DEPTH=0
inherit() {
	ECLASS_DEPTH=$(($ECLASS_DEPTH + 1))
	if [[ ${ECLASS_DEPTH} > 1 ]]; then
		debug-print "*** Multiple Inheritence (Level: ${ECLASS_DEPTH})"
	fi

	local location
	local PECLASS

	local B_IUSE
	local B_DEPEND
	local B_RDEPEND
	local B_PDEPEND
	while [ "$1" ]; do
		location="${ECLASSDIR}/${1}.eclass"

		# PECLASS is used to restore the ECLASS var after recursion.
		PECLASS="$ECLASS"
		export ECLASS="$1"

		if [ "$EBUILD_PHASE" != "depend" ]; then
			if ! hasq $ECLASS $INHERITED; then
				echo
				echo "QA Notice: ECLASS '$ECLASS' inherited illegally in $CATEGORY/$PF" >&2
				echo
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

		#We need to back up the value of DEPEND and RDEPEND to B_DEPEND and B_RDEPEND
		#(if set).. and then restore them after the inherit call.

		#turn off glob expansion
		set -f

		# Retain the old data and restore it later.
		unset B_IUSE B_DEPEND B_RDEPEND B_PDEPEND
		[ "${IUSE-unset}"    != "unset" ] && B_IUSE="${IUSE}"
		[ "${DEPEND-unset}"  != "unset" ] && B_DEPEND="${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && B_RDEPEND="${RDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && B_PDEPEND="${PDEPEND}"
		unset IUSE DEPEND RDEPEND PDEPEND
		#turn on glob expansion
		set +f

		source "$location" || export ERRORMSG="died sourcing $location in inherit()"
		[ -z "${ERRORMSG}" ] || die "${ERRORMSG}"

		#turn off glob expansion
		set -f

		# If each var has a value, append it to the global variable E_* to
		# be applied after everything is finished. New incremental behavior.
		[ "${IUSE-unset}"    != "unset" ] && export E_IUSE="${E_IUSE} ${IUSE}"
		[ "${DEPEND-unset}"  != "unset" ] && export E_DEPEND="${E_DEPEND} ${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && export E_RDEPEND="${E_RDEPEND} ${RDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && export E_PDEPEND="${E_PDEPEND} ${PDEPEND}"

		[ "${B_IUSE-unset}"    != "unset" ] && IUSE="${B_IUSE}"
		[ "${B_IUSE-unset}"    != "unset" ] || unset IUSE

		[ "${B_DEPEND-unset}"  != "unset" ] && DEPEND="${B_DEPEND}"
		[ "${B_DEPEND-unset}"  != "unset" ] || unset DEPEND

		[ "${B_RDEPEND-unset}" != "unset" ] && RDEPEND="${B_RDEPEND}"
		[ "${B_RDEPEND-unset}" != "unset" ] || unset RDEPEND

		[ "${B_PDEPEND-unset}" != "unset" ] && PDEPEND="${B_PDEPEND}"
		[ "${B_PDEPEND-unset}" != "unset" ] || unset PDEPEND

		#turn on glob expansion
		set +f

		hasq $1 $INHERITED || export INHERITED="$INHERITED $1"

		export ECLASS="$PECLASS"

		shift
	done
	ECLASS_DEPTH=$(($ECLASS_DEPTH - 1))
}

# Exports stub functions that call the eclass's functions, thereby making them default.
# For example, if ECLASS="base" and you call "EXPORT_FUNCTIONS src_unpack", the following
# code will be eval'd:
# src_unpack() { base_src_unpack; }
EXPORT_FUNCTIONS() {
	if [ -z "$ECLASS" ]; then
		echo "EXPORT_FUNCTIONS without a defined ECLASS" >&2
		exit 1
	fi
	while [ "$1" ]; do
		debug-print "EXPORT_FUNCTIONS: ${1} -> ${ECLASS}_${1}"
		eval "$1() { ${ECLASS}_$1 "\$@" ; }" > /dev/null
		shift
	done
}

# adds all parameters to E_DEPEND and E_RDEPEND, which get added to DEPEND
# and RDEPEND after the ebuild has been processed. This is important to
# allow users to use DEPEND="foo" without frying dependencies added by an
# earlier inherit. It also allows RDEPEND to work properly, since a lot
# of ebuilds assume that an unset RDEPEND gets its value from DEPEND.
# Without eclasses, this is true. But with them, the eclass may set
# RDEPEND itself (or at least used to) which would prevent RDEPEND from
# getting its value from DEPEND. This is a side-effect that made eclasses
# have unreliable dependencies.

newdepend() {
	debug-print-function newdepend $*
	debug-print "newdepend: E_DEPEND=$E_DEPEND E_RDEPEND=$E_RDEPEND"

	while [ -n "$1" ]; do
		case $1 in
		"/autotools")
			do_newdepend DEPEND sys-devel/autoconf sys-devel/automake sys-devel/make
			;;
		"/c")
			do_newdepend DEPEND sys-devel/gcc virtual/libc
			do_newdepend RDEPEND virtual/libc
			;;
		*)
			do_newdepend DEPEND $1
			;;
		esac
		shift
	done
}

newrdepend() {
	debug-print-function newrdepend $*
	do_newdepend RDEPEND $1
}

newpdepend() {
	debug-print-function newpdepend $*
	do_newdepend PDEPEND $1
}

do_newdepend() {
	# This function does a generic change determining whether we're in an
	# eclass or not. If we are, we change the E_* variables for deps.
	debug-print-function do_newdepend $*
	[ -z "$1" ] && die "do_newdepend without arguments"

	# Grab what we're affecting... Figure out if we're affecting eclasses.
	[[ ${ECLASS_DEPTH} > 0 ]] && TARGET="E_$1"
	[[ ${ECLASS_DEPTH} > 0 ]] || TARGET="$1"
	shift # $1 was a variable name.

	while [ -n "$1" ]; do
		# This bit of evil takes TARGET and uses it to evaluate down to a
		# variable. This is a sneaky way to make this infinately expandable.
		# The normal translation of this would look something like this:
		# E_DEPEND="${E_DEPEND} $1"  ::::::  Cool, huh? :)
		eval export ${TARGET}=\"\${${TARGET}} \$1\"
		shift
	done
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

# === === === === === === === === === === === === === === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === functions end, main part begins === === === === ===
# === === === === === === === === === === === === === === === === === ===

if [ "$*" != "depend" ] && [ "$*" != "clean" ] && [ "$*" != "setup" ]; then
	cd ${PORTAGE_TMPDIR} &> /dev/null
	cd ${BUILD_PREFIX} &> /dev/null

	if [ "$(id -nu)" == "portage" ] ; then
		export USER=portage
	fi

	if hasq distcc ${FEATURES} &>/dev/null; then
		if [ -d /usr/lib/distcc/bin ]; then
			#We can enable distributed compile support
			if [ -z "${PATH/*distcc*/}" ]; then
				# Remove the other reference.
				remove_path_entry "distcc"
			fi
			export PATH="/usr/lib/distcc/bin:${PATH}"
			[ ! -z "${DISTCC_LOG}" ] && addwrite "$(dirname ${DISTCC_LOG})"
		elif which distcc &>/dev/null; then
			export CC="distcc $CC"
			export CXX="distcc $CXX"
		fi
	fi

	if hasq ccache ${FEATURES} &>/dev/null; then
		#We can enable compiler cache support
		if [ -z "${PATH/*ccache*/}" ]; then
			# Remove the other reference.
			remove_path_entry "ccache"
		fi

		if [ -d /usr/lib/ccache/bin ]; then
			export PATH="/usr/lib/ccache/bin:${PATH}"
		elif [ -d /usr/bin/ccache ]; then
			export PATH="/usr/bin/ccache:${PATH}"
		fi

		[ -z "${CCACHE_DIR}" ] && export CCACHE_DIR="/var/tmp/ccache"

		addread "${CCACHE_DIR}"
		addwrite "${CCACHE_DIR}"

		[ -n "${CCACHE_SIZE}" ] && ccache -M ${CCACHE_SIZE} &> /dev/null
	fi

	# XXX: Load up the helper functions.
#	for X in /usr/lib/portage/bin/functions/*.sh; do
#		source ${X} || die "Failed to source ${X}"
#	done

else

killparent() {
	trap INT
	kill ${PORTAGE_MASTER_PID}
}
trap "killparent" INT

fi # "$*"!="depend" && "$*"!="clean" && "$*" != "setup"

export SANDBOX_ON="1"
export S=${WORKDIR}/${P}

unset E_IUSE E_DEPEND E_RDEPEND E_PDEPEND

for x in T P PN PV PVR PR A EBUILD EMERGE_FROM O PPID FILESDIR PORTAGE_TMPDIR; do
	[[ ${!x-UNSET_VAR} != UNSET_VAR ]] && declare -r ${x}
done
# Need to be able to change D in dyn_preinst due to the IMAGE stuff
[[ $* != "preinst" ]] && declare -r D
unset x

# Turn of extended glob matching so that g++ doesn't get incorrectly matched.
shopt -u extglob

QA_INTERCEPTORS="javac java-config python python-config perl grep egrep fgrep sed gcc g++ cc bash awk nawk gawk pkg-config"
# level the QA interceptors if we're in depend
if hasq "depend" "$@"; then
	for BIN in ${QA_INTERCEPTORS}; do
		BIN_PATH=`type -pf ${BIN}`
		if [ "$?" != "0" ]; then
			BODY="echo \"*** missing command: ${BIN}\" >&2; return 127"
		else
			BODY="${BIN_PATH} \"\$@\"; return \$?"
		fi
		FUNC_SRC="${BIN}() {
		echo -n \"QA Notice: ${BIN} in global scope: \" >&2
		if [ \$ECLASS_DEPTH -gt 0 ]; then
			echo \"eclass \${ECLASS}\" >&2
		else
			echo \"\${CATEGORY}/\${PF}\" >&2
		fi
		${BODY}
		}";
		eval "$FUNC_SRC" || echo "error creating QA interceptor ${BIN}" >&2
	done
	unset src bin_path body
fi

# reset the EBUILD_DEATH_HOOKS so they don't multiple due to stable's re-sourcing of env.
# this can be left out of ebd variants, since they're unaffected.
unset EBUILD_DEATH_HOOKS

source ${EBUILD} || die "error sourcing ebuild"
if ! hasq depend $EBUILD_PHASE; then
	RESTRICT="${PORTAGE_RESTRICT}"
	unset PORTAGE_RESTRICT
fi
[ -z "${ERRORMSG}" ] || die "${ERRORMSG}"

# Expand KEYWORDS
# We need to turn off pathname expansion for -* in KEYWORDS and
# we need to escape ~ to avoid tilde expansion
set -f
KEYWORDS="`eval echo ${KEYWORDS//~/\\~}`"
set +f

hasq nostrip ${RESTRICT} && export DEBUGBUILD=1

#a reasonable default for $S
if [ "$S" = "" ]; then
	export S=${WORKDIR}/${P}
fi

#wipe the interceptors.  we don't want saved.
if hasq "depend" "$@"; then
	unset -f $QA_INTERCEPTORS
	unset QA_INTERCEPTORS
fi

#some users have $TMP/$TMPDIR to a custom dir in their home ...
#this will cause sandbox errors with some ./configure
#scripts, so set it to $T.
export TMP="${T}"
export TMPDIR="${T}"

# Note: this next line is not the same as export RDEPEND=${RDEPEND:-${DEPEND}}
# That will test for unset *or* NULL ("").  We want just to set for unset...

#turn off glob expansion from here on in to prevent *'s and ? in the DEPEND
#syntax from getting expanded :)  Fixes bug #1473
#check eclass rdepends also. bug #58819
set -f
if [ "${RDEPEND-unset}" == "unset" ] && [ "${E_RDEPEND-unset}" == "unset" ] ; then
	export RDEPEND="${DEPEND} ${E_DEPEND}"
	debug-print "RDEPEND: not set... Setting to: ${DEPEND}"
fi

#add in dependency info from eclasses
IUSE="$IUSE $E_IUSE"
DEPEND="$DEPEND $E_DEPEND"
RDEPEND="$RDEPEND $E_RDEPEND"
PDEPEND="$PDEPEND $E_PDEPEND"

unset E_IUSE E_DEPEND E_RDEPEND E_PDEPEND

if [ "${EBUILD_PHASE}" != "depend" ]; then
	# Lock the dbkey variables after the global phase
	declare -r DEPEND RDEPEND SLOT SRC_URI RESTRICT HOMEPAGE LICENSE DESCRIPTION
	declare -r KEYWORDS INHERITED IUSE PDEPEND PROVIDE
fi

set +f

for myarg in $*; do
	case $myarg in
	nofetch)
		pkg_nofetch
		exit 1
		;;
	prerm|postrm|postinst|config)
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" != "1" ]; then
			[ "$(type -t pre_pkg_${myarg})" == "function" ] && pre_pkg_${myarg}
			pkg_${myarg}
			[ "$(type -t post_pkg_${myarg})" == "function" ] && post_pkg_${myarg}
			#Allow non-zero return codes since they can be caused by &&
		else
			set -x
			[ "$(type -t pre_pkg_${myarg})" == "function" ] && pre_pkg_${myarg}
			pkg_${myarg}
			[ "$(type -t post_pkg_${myarg})" == "function" ] && post_pkg_${myarg}
			#Allow non-zero return codes since they can be caused by &&
			set +x
		fi
		;;
	unpack|compile|test|clean|install)
		if [ "${SANDBOX_DISABLED="0"}" == "0" ]; then
			export SANDBOX_ON="1"
		else
			export SANDBOX_ON="0"
		fi
		if [ "$PORTAGE_DEBUG" != "1" ]; then
			dyn_${myarg}
			#Allow non-zero return codes since they can be caused by &&
		else
			set -x
			dyn_${myarg}
			#Allow non-zero return codes since they can be caused by &&
			set +x
		fi
		export SANDBOX_ON="0"
		;;
	help|clean|setup|preinst)
		#pkg_setup needs to be out of the sandbox for tmp file creation;
		#for example, awking and piping a file in /tmp requires a temp file to be created
		#in /etc.  If pkg_setup is in the sandbox, both our lilo and apache ebuilds break.
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" != "1" ]; then
			dyn_${myarg}
		else
			set -x
			dyn_${myarg}
			set +x
		fi
		;;
	package|rpm)
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" != "1" ]; then
			dyn_${myarg}
		else
			set -x
			dyn_${myarg}
			set +x
		fi
		;;
	depend)
		export SANDBOX_ON="0"
		set -f

		# Handled in portage.py now
		#dbkey=${PORTAGE_CACHEDIR}/${CATEGORY}/${PF}

		if [ ! -d "${dbkey%/*}" ]; then
			install -d -g ${PORTAGE_GID} -m2775 "${dbkey%/*}"
		fi

		# Make it group writable. 666&~002==664
		umask 002

		#the extra `echo` commands remove newlines
		echo `echo "$DEPEND"`       > $dbkey
		echo `echo "$RDEPEND"`     >> $dbkey
		echo `echo "$SLOT"`        >> $dbkey
		echo `echo "$SRC_URI"`     >> $dbkey
		echo `echo "$RESTRICT"`    >> $dbkey
		echo `echo "$HOMEPAGE"`    >> $dbkey
		echo `echo "$LICENSE"`     >> $dbkey
		echo `echo "$DESCRIPTION"` >> $dbkey
		echo `echo "$KEYWORDS"`    >> $dbkey
		echo `echo "$INHERITED"`   >> $dbkey
		echo `echo "$IUSE"`        >> $dbkey
		echo                       >> $dbkey
		echo `echo "$PDEPEND"`     >> $dbkey
		echo `echo "$PROVIDE"`     >> $dbkey
		echo `echo "${EAPI:-0}"`   >> $dbkey
		echo `echo "$UNUSED_01"`   >> $dbkey
		echo `echo "$UNUSED_02"`   >> $dbkey
		echo `echo "$UNUSED_03"`   >> $dbkey
		echo `echo "$UNUSED_04"`   >> $dbkey
		echo `echo "$UNUSED_05"`   >> $dbkey
		echo `echo "$UNUSED_06"`   >> $dbkey
		echo `echo "$UNUSED_07"`   >> $dbkey
		set +f
		#make sure it is writable by our group:
		exit 0
		;;
	*)
		export SANDBOX_ON="1"
		echo "Please specify a valid command."
		echo
		dyn_help
		exit 1
		;;
	esac

	#if [ $? -ne 0 ]; then
	#	exit 1
	#fi
done

if [ "$myarg" != "clean" ]; then
	# Save current environment and touch a success file. (echo for success)
	umask 002
	set | egrep -v "^SANDBOX_" > "${T}/environment" 2>/dev/null
	chown portage:portage "${T}/environment" &>/dev/null
	chmod g+w "${T}/environment" &>/dev/null
fi

exit 0
