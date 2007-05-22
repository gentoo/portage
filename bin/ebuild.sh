#!/bin/bash
# Copyright 1999-2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

PORTAGE_BIN_PATH="${PORTAGE_BIN_PATH:-/usr/lib/portage/bin}"
PORTAGE_PYM_PATH="${PORTAGE_PYM_PATH:-/usr/lib/portage/pym}"
declare -rx PORTAGE_BIN_PATH PORTAGE_PYM_PATH

SANDBOX_PREDICT="${SANDBOX_PREDICT}:/proc/self/maps:/dev/console:/dev/random"
export SANDBOX_PREDICT="${SANDBOX_PREDICT}:${PORTAGE_PYM_PATH}:${PORTAGE_DEPCACHEDIR}"
export SANDBOX_WRITE="${SANDBOX_WRITE}:/dev/shm:/dev/stdout:/dev/stderr:${PORTAGE_TMPDIR}"
export SANDBOX_READ="${SANDBOX_READ}:/dev/shm:/dev/stdin:${PORTAGE_TMPDIR}"

if [ ! -z "${PORTAGE_GPG_DIR}" ]; then
	SANDBOX_PREDICT="${SANDBOX_PREDICT}:${PORTAGE_GPG_DIR}"
fi

declare -rx EBUILD_PHASE

if [ "$*" != "depend" ] && [ "$*" != "clean" ] && [ "$*" != "nofetch" ]; then
	if [ -f "${T}/environment" ]; then
		source "${T}/environment" >& /dev/null
	fi
fi

# These two functions wrap sourcing and calling respectively.  At present they
# perform a qa check to make sure eclasses and ebuilds and profiles don't mess
# with shell opts (shopts).  Ebuilds/eclasses changing shopts should reset them 
# when they are done.  Note:  For now these shoudl always return success.

qa_source() {
	local shopts=$(shopt) OLDIFS="$IFS"
	source "$@" || return 1
	[[ $shopts != $(shopt) ]] &&
		eqawarn "QA Notice: Global shell options changed and were not restored while sourcing '$*'"
	[[ "$IFS" != "$OLDIFS" ]] &&
		eqawarn "QA Notice: Global IFS changed and was not restored while sourcing '$*'"
	return 0
}

qa_call() {
	local shopts=$(shopt) OLDIFS="$IFS"
	"$@" || return 1
	[[ $shopts != $(shopt) ]] &&
		eqawarn "QA Notice: Global shell options changed and were not restored while calling '$*'"
	[[ "$IFS" != "$OLDIFS" ]] &&
		eqawarn "QA Notice: Global IFS changed and was not restored while calling '$*'"
	return 0
}

# subshell die support
EBUILD_MASTER_PID=$$
trap 'exit 1' SIGTERM

EBUILD_SH_ARGS="$*"

shift $#

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# Unset some variables that break things.
unset GZIP BZIP BZIP2 CDPATH GREP_OPTIONS GREP_COLOR GLOBIGNORE

export PATH="/usr/local/sbin:/sbin:/usr/sbin:${PORTAGE_BIN_PATH}:/usr/local/bin:/bin:/usr/bin:${ROOTPATH}"
[ ! -z "$PREROOTPATH" ] && export PATH="${PREROOTPATH%%:}:$PATH"

source "${PORTAGE_BIN_PATH}/isolated-functions.sh"  &>/dev/null

OCC="$CC"
OCXX="$CXX"

[[ $PORTAGE_QUIET != "" ]] && export PORTAGE_QUIET

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON="0"

# sandbox support functions; defined prior to profile.bashrc srcing, since the profile might need to add a default exception (/usr/lib64/conftest fex)
addread() {
	[[ -z $1 || -n $2 ]] && die "Usage: addread <colon-delimited list of paths>"
	export SANDBOX_READ="$SANDBOX_READ:$1"
}

addwrite() {
	[[ -z $1 || -n $2 ]] && die "Usage: addwrite <colon-delimited list of paths>"
	export SANDBOX_WRITE="$SANDBOX_WRITE:$1"
}

adddeny() {
	[[ -z $1 || -n $2 ]] && die "Usage: adddeny <colon-delimited list of paths>"
	export SANDBOX_DENY="$SANDBOX_DENY:$1"
}

addpredict() {
	[[ -z $1 || -n $2 ]] && die "Usage: addpredict <colon-delimited list of paths>"
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
		qa_source "${dir}/profile.bashrc"
	fi
done
restore_IFS

# We assume if people are changing shopts in their bashrc they do so at their
# own peril.  This is the ONLY non-portage bit of code that can change shopts
# without a QA violation.
if [ -f "${PORTAGE_BASHRC}" ]; then
	# If $- contains x, then tracing has already enabled elsewhere for some
	# reason.  We preserve it's state so as not to interfere.
	if [ "$PORTAGE_DEBUG" != "1" ] || [ "${-/x/}" != "$-" ]; then
		source "${PORTAGE_BASHRC}"
	else
		set -x
		source "${PORTAGE_BASHRC}"
		set +x
	fi
fi

[ ! -z "$OCC" ] && export CC="$OCC"
[ ! -z "$OCXX" ] && export CXX="$OCXX"

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
		echo "${1}"
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

	# Make sure we have this USE flag in IUSE
	if ! hasq "${u}" ${IUSE} ${E_IUSE} && ! hasq "${u}" ${PORTAGE_ARCHLIST} selinux; then
		eqawarn "QA Notice: USE Flag '${u}' not in IUSE for ${CATEGORY}/${PF}"
	fi

	if hasq ${u} ${USE} ; then
		return ${found}
	else
		return $((!found))
	fi
}

has_version() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls (has_version calls portageq) are not allowed in the global scope"
	fi
	# return shell-true/shell-false if exists.
	# Takes single depend-type atoms.
	if "${PORTAGE_BIN_PATH}/portageq" 'has_version' "${ROOT}" "$1"; then
		return 0
	else
		return 1
	fi
}

portageq() {
	if [ "${EBUILD_PHASE}" == "depend" ]; then
		die "portageq calls are not allowed in the global scope"
	fi
	"${PORTAGE_BIN_PATH}/portageq" "$@"
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
	"${PORTAGE_BIN_PATH}/portageq" 'best_version' "${ROOT}" "$1"
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

check_KV() {
	if [ -z "${KV}" ]; then
		eerror ""
		eerror "Could not determine your kernel version."
		eerror "Make sure that you have a /usr/src/linux symlink,"
		eerror "and that the indicated kernel has been configured."
		eerror "You can also simply run the following command"
		eerror "in the directory referenced by /usr/src/linux:"
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
		find "$@" -type d -printf "${D}/%p/.keep_${CATEGORY}_${PN}-${SLOT}\n" | tr "\n" "\0" | $XARGS -0 -n100 touch || die "Failed to recursively create .keep files"
	else
		for x in "$@"; do
			touch "${D}/${x}/.keep_${CATEGORY}_${PN}-${SLOT}" || die "Failed to create .keep in ${D}/${x}"
		done
	fi
}

unpack() {
	local x
	local y
	local myfail
	local tar_opts=""
	[ -z "$*" ] && die "Nothing passed to the 'unpack' command"

	for x in "$@"; do
		vecho ">>> Unpacking ${x} to ${PWD}"
		y=${x%.*}
		y=${y##*.}

		myfail="${x} does not exist"
		if [ "${x:0:2}" = "./" ] ; then
			srcdir=""
		else
			srcdir="${DISTDIR}/"
		fi
		[[ ${x} == ${DISTDIR}* ]] && \
			die "Arguments to unpack() should not begin with \${DISTDIR}."
		[ ! -s "${srcdir}${x}" ] && die "$myfail"

		myfail="failure unpacking ${x}"
		case "${x##*.}" in
			tar)
				tar xof "${srcdir}${x}" ${tar_opts} || die "$myfail"
				;;
			tgz)
				tar xozf "${srcdir}${x}" ${tar_opts} || die "$myfail"
				;;
			tbz|tbz2)
				bzip2 -dc "${srcdir}${x}" | tar xof - ${tar_opts}
				assert "$myfail"
				;;
			ZIP|zip|jar)
				unzip -qo "${srcdir}${x}" || die "$myfail"
				;;
			gz|Z|z)
				if [ "${y}" == "tar" ]; then
					tar zoxf "${srcdir}${x}" ${tar_opts} || die "$myfail"
				else
					gzip -dc "${srcdir}${x}" > ${x%.*} || die "$myfail"
				fi
				;;
			bz2|bz)
				if [ "${y}" == "tar" ]; then
					bzip2 -dc "${srcdir}${x}" | tar xof - ${tar_opts}
					assert "$myfail"
				else
					bzip2 -dc "${srcdir}${x}" > ${x%.*} || die "$myfail"
				fi
				;;
			7Z|7z)
				local my_output
				my_output="$(7z x -y "${srcdir}/${x}")"
				if [ $? -ne 0 ]; then
					echo "${my_output}" >&2
					die "$myfail"
				fi
				;;
			RAR|rar)
				unrar x -idq -o+ "${srcdir}/${x}" || die "$myfail"
				;;
			LHa|LHA|lha|lzh)
				lha xqf "${srcdir}/${x}" || die "$myfail"
				;;
			a|deb)
				ar x "${srcdir}/${x}" || die "$myfail"
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

econf() {
	local x
	local LOCAL_EXTRA_ECONF="${EXTRA_ECONF}"

	if [ -z "${ECONF_SOURCE}" ]; then
		ECONF_SOURCE="."
	fi
	if [ -x "${ECONF_SOURCE}/configure" ]; then
		if [ -e /usr/share/gnuconfig/ ]; then
			for x in $(find "${WORKDIR}" -type f '(' -name config.guess -o -name config.sub ')') ; do
				vecho " * econf: updating ${x/${WORKDIR}\/} with /usr/share/gnuconfig/${x##*/}"
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

			CONF_LIBDIR_RESULT="$(strip_duplicate_slashes ${CONF_PREFIX}${CONF_LIBDIR})"

			LOCAL_EXTRA_ECONF="--libdir=${CONF_LIBDIR_RESULT} ${LOCAL_EXTRA_ECONF}"
		fi

		local TMP_CONFCACHE_DIR CONFCACHE_ARG
		if hasq confcache $FEATURES && ! hasq confcache $RESTRICT; then
			CONFCACHE="$(type -P confcache)"
			if [ -z "${CONFCACHE}" ]; then
				ewarn "disabling confcache, binary cannot be found"
			else
				CONFCACHE="${CONFCACHE/ /\ }"
				TMP_CONFCACHE_DIR="${CONFCACHE:+${CONFCACHE_DIR:-${PORTAGE_TMPDIR}/confcache}}"
				TMP_CONFCACHE_DIR="${TMP_CONFCACHE_DIR/ /\ }"
				CONFCACHE_ARG="--confcache-dir"
				local s
				if [ -n "$CCACHE_DIR" ]; then
					s="$CCACHE_DIR"
				fi
				if [ -n "$DISTCC_DIR" ]; then
					s="${s:+${s}:}$DISTCC_DIR"
				fi
				if [ -n "$s" ]; then
					CONFCACHE_ARG="--confcache-ignore $s $CONFCACHE_ARG"
				fi
			fi
		else
			CONFCACHE=
		fi

		vecho ${CONFCACHE} ${CONFCACHE_ARG} ${TMP_CONFCACHE_DIR} "${ECONF_SOURCE}/configure" \
			--prefix=/usr \
			--host=${CHOST} \
			--mandir=/usr/share/man \
			--infodir=/usr/share/info \
			--datadir=/usr/share \
			--sysconfdir=/etc \
			--localstatedir=/var/lib \
			"$@" \
			${LOCAL_EXTRA_ECONF}

		if ! ${CONFCACHE} ${CONFCACHE_ARG} ${TMP_CONFCACHE_DIR} "${ECONF_SOURCE}/configure" \
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
	local LOCAL_EXTRA_EINSTALL="${EXTRA_EINSTALL}"
	LIBDIR_VAR="LIBDIR_${ABI}"
	if [ -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
		CONF_LIBDIR="${!LIBDIR_VAR}"
	fi
	unset LIBDIR_VAR
	if [ -n "${CONF_LIBDIR}" ] && [ "${CONF_PREFIX:-unset}" != "unset" ]; then
		EI_DESTLIBDIR="${D}/${CONF_PREFIX}/${CONF_LIBDIR}"
		EI_DESTLIBDIR="$(strip_duplicate_slashes ${EI_DESTLIBDIR})"
		LOCAL_EXTRA_EINSTALL="libdir=${EI_DESTLIBDIR} ${LOCAL_EXTRA_EINSTALL}"
		unset EI_DESTLIBDIR
	fi

	if [ -f ./[mM]akefile -o -f ./GNUmakefile ] ; then
		if [ "${PORTAGE_DEBUG}" == "1" ]; then
			make -n prefix="${D}/usr" \
				datadir="${D}/usr/share" \
				infodir="${D}/usr/share/info" \
				localstatedir="${D}/var/lib" \
				mandir="${D}/usr/share/man" \
				sysconfdir="${D}/etc" \
				${LOCAL_EXTRA_EINSTALL} \
				"$@" install
		fi
		make prefix="${D}/usr" \
			datadir="${D}/usr/share" \
			infodir="${D}/usr/share/info" \
			localstatedir="${D}/var/lib" \
			mandir="${D}/usr/share/man" \
			sysconfdir="${D}/etc" \
			${LOCAL_EXTRA_EINSTALL} \
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
	local x
	for x in $(echo ${SRC_URI}); do
		echo "!!!   ${x}"
	done
}

src_unpack() {
	[[ -n ${A} ]] && unpack ${A}
}

src_compile() {
	if [ "${EAPI:-0}" == 0 ] ; then
		[ -x ./configure ] && econf
	elif [ -x "${ECONF_SOURCE:-.}/configure" ] ; then
		econf
	fi
	if [ -f Makefile ] || [ -f GNUmakefile ] || [ -f makefile ]; then
		emake || die "emake failed"
	fi
}

src_test() {
	if emake -j1 check -n &> /dev/null; then
		vecho ">>> Test phase [check]: ${CATEGORY}/${PF}"
		if ! emake -j1 check; then
			hasq test $FEATURES && die "Make check failed. See above for details."
			hasq test $FEATURES || eerror "Make check failed. See above for details."
		fi
	elif emake -j1 test -n &> /dev/null; then
		vecho ">>> Test phase [test]: ${CATEGORY}/${PF}"
		if ! emake -j1 test; then
			hasq test $FEATURES && die "Make test failed. See above for details."
			hasq test $FEATURES || eerror "Make test failed. See above for details."
		fi
	else
		vecho ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
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
	cat > "$1" <<-EOF
	#!/bin/sh
	exec $2 "\$@"
	EOF
	chmod 0755 "$1"
}

dyn_setup() {
	[ "$(type -t pre_pkg_setup)" == "function" ] && qa_call pre_pkg_setup
	qa_call pkg_setup
	[ "$(type -t post_pkg_setup)" == "function" ] && qa_call post_pkg_setup
}

dyn_unpack() {
	[ "$(type -t pre_src_unpack)" == "function" ] && qa_call pre_src_unpack
	local newstuff="no"
	if [ -e "${WORKDIR}" ]; then
		local x
		local checkme
		for x in ${AA}; do
			vecho ">>> Checking ${x}'s mtime..."
			if [ "${PORTAGE_ACTUAL_DISTDIR:-${DISTDIR}}/${x}" -nt "${WORKDIR}" ]; then
				vecho ">>> ${x} has been updated; recreating WORKDIR..."
				newstuff="yes"
				break
			fi
		done
		if [ "${EBUILD}" -nt "${WORKDIR}" ] && ! hasq keepwork ${FEATURES} ; then
			vecho ">>> ${EBUILD} has been updated; recreating WORKDIR..."
			newstuff="yes"
		elif [ ! -f "${PORTAGE_BUILDDIR}/.unpacked" ]; then
			vecho ">>> Not marked as unpacked; recreating WORKDIR..."
			newstuff="yes"
		fi
	fi
	if [ "${newstuff}" == "yes" ]; then
		# We don't necessarily have privileges to do a full dyn_clean here.
		rm -rf "${WORKDIR}"
		if [ -d "${T}" ] && ! hasq keeptemp ${FEATURES} ; then
			rm -rf "${T}" && mkdir "${T}"
		else
			[ -e "${T}/environment" ] && \
				mv "${T}/environment" "${T}/environment.keeptemp"
		fi
	fi
	if [ -e "${WORKDIR}" ]; then
		if [ "$newstuff" == "no" ]; then
			vecho ">>> WORKDIR is up-to-date, keeping..."
			[ "$(type -t post_src_unpack)" == "function" ] && qa_call post_src_unpack
			return 0
		fi
	fi

	if [ ! -d "${WORKDIR}" ]; then
		install -m${PORTAGE_WORKDIR_MODE:-0700} -d "${WORKDIR}" || die "Failed to create dir '${WORKDIR}'"
	fi
	cd "${WORKDIR}" || die "Directory change failed: \`cd '${WORKDIR}'\`"
	vecho ">>> Unpacking source..."
	qa_call src_unpack
	touch "${PORTAGE_BUILDDIR}/.unpacked" || die "IO Failure -- Failed 'touch .unpacked' in ${PORTAGE_BUILDDIR}"
	vecho ">>> Source unpacked."
	cd "${PORTAGE_BUILDDIR}"

	[ "$(type -t post_src_unpack)" == "function" ] && qa_call post_src_unpack
}

dyn_clean() {
	if [ -z "${PORTAGE_BUILDDIR}" ]; then
		echo "Aborting clean phase because PORTAGE_BUILDDIR is unset!"
		return 1
	fi

	if type -P chflags > /dev/null ; then
		chflags -R noschg,nouchg,nosappnd,nouappnd "${PORTAGE_BUILDDIR}"
		chflags -R nosunlnk,nouunlnk "${PORTAGE_BUILDDIR}" 2>/dev/null
	fi

	rm -rf "${PORTAGE_BUILDDIR}/image" "${PORTAGE_BUILDDIR}/homedir"

	if ! hasq keeptemp $FEATURES; then
		rm -rf "${T}"
	else
		[ -e "${T}/environment" ] && mv "${T}/environment" "${T}/environment.keeptemp"
	fi

	if ! hasq keepwork $FEATURES; then
		rm -rf "${PORTAGE_BUILDDIR}/.logid"
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

	# do not bind this to doebuild defined DISTDIR; don't trust doebuild, and if mistakes are made it'll
	# result in it wiping the users distfiles directory (bad).
	rm -rf "${PORTAGE_BUILDDIR}/distdir"

	if [ -z "$(find "${PORTAGE_BUILDDIR}" -mindepth 1 -maxdepth 1)" ]; then
		rmdir "${PORTAGE_BUILDDIR}"
	fi

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
		export _E_EXEDESTTREE_=""
	else
		export _E_EXEDESTTREE_="$1"
		if [ ! -d "${D}${_E_EXEDESTTREE_}" ]; then
			install -d "${D}${_E_EXEDESTTREE_}"
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

	[ "$(type -t pre_src_compile)" == "function" ] && qa_call pre_src_compile

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

	LIBDIR_VAR="LIBDIR_${ABI}"
	if [ -z "${PKG_CONFIG_PATH}" -a -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
		export PKG_CONFIG_PATH="/usr/${!LIBDIR_VAR}/pkgconfig"
	fi
	unset LIBDIR_VAR

	if hasq noauto $FEATURES && [ ! -f ${PORTAGE_BUILDDIR}/.unpacked ]; then
		echo
		echo "!!! We apparently haven't unpacked... This is probably not what you"
		echo "!!! want to be doing... You are using FEATURES=noauto so I'll assume"
		echo "!!! that you know what you are doing... You have 5 seconds to abort..."
		echo

		local x
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

	if [[ ${PORTAGE_BUILDDIR}/.compiled -nt ${WORKDIR} ]] ; then
		vecho ">>> It appears that '${PF}' is already compiled; skipping."
		vecho ">>> Remove '${PORTAGE_BUILDDIR}/.compiled' to force compilation."
		trap SIGINT SIGQUIT
		[ "$(type -t post_src_compile)" == "function" ] && qa_call post_src_compile
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
	vecho ">>> Compiling source in ${srcdir} ..."
	qa_call src_compile
	vecho ">>> Source compiled."
	#|| abort_compile "fail"
	cd "${PORTAGE_BUILDDIR}"
	touch .compiled
	cd build-info

	set -f
	for f in ASFLAGS CATEGORY CBUILD CC CFLAGS CHOST CTARGET CXX \
		CXXFLAGS DEPEND EXTRA_ECONF EXTRA_EINSTALL EXTRA_MAKE \
		FEATURES INHERITED IUSE LDFLAGS LIBCFLAGS LIBCXXFLAGS \
		LICENSE PDEPEND PF PKGUSE PROVIDE RDEPEND RESTRICT SLOT \
		KEYWORDS HOMEPAGE SRC_URI DESCRIPTION; do
		[ -n "${!f}" ] && echo $(echo "${!f}" | tr '\n,\r,\t' ' , , ' | sed s/'  \+'/' '/g) > ${f}
	done
	echo "${USE}"		> USE
	echo "${EAPI:-0}"	> EAPI
	set +f
	set                     >  environment
	export | sed 's:^declare -rx:declare -x:' >> environment
	bzip2 -f9 environment

	cp "${EBUILD}" "${PF}.ebuild"
	if hasq nostrip ${FEATURES} ${RESTRICT} || hasq strip ${RESTRICT}
	then
		touch DEBUGBUILD
	fi

	[ "$(type -t post_src_compile)" == "function" ] && qa_call post_src_compile

	trap SIGINT SIGQUIT
}

dyn_test() {
	if [ "${EBUILD_FORCE_TEST}" == "1" ] ; then
		rm -f "${PORTAGE_BUILDDIR}/.tested"
		# If USE came from ${T}/environment then it might not have USE=test
		# like it's supposed to here.
		! hasq test ${USE} && export USE="${USE} test"
	fi
	[ "$(type -t pre_src_test)" == "function" ] && qa_call pre_src_test
	if [ "${PORTAGE_BUILDDIR}/.tested" -nt "${WORKDIR}" ]; then
		vecho ">>> It appears that ${PN} has already been tested; skipping."
		[ "$(type -t post_src_test)" == "function" ] && qa_call post_src_test
		return
	fi
	trap "abort_test" SIGINT SIGQUIT
	if [ -d "${S}" ]; then
		cd "${S}"
	fi
	if ! hasq test $FEATURES && [ "${EBUILD_FORCE_TEST}" != "1" ]; then
		vecho ">>> Test phase [not enabled]: ${CATEGORY}/${PF}"
	elif ! hasq test ${USE} && [ "${EBUILD_FORCE_TEST}" != "1" ]; then
		ewarn "Skipping make test/check since USE=test is masked."
		vecho ">>> Test phase [explicitly disabled]: ${CATEGORY}/${PF}"
	elif hasq test $RESTRICT; then
		ewarn "Skipping make test/check due to ebuild restriction."
		vecho ">>> Test phase [explicitly disabled]: ${CATEGORY}/${PF}"
	else
		addpredict /
		qa_call src_test
		SANDBOX_PREDICT="${SANDBOX_PREDICT%:/}"
	fi

	cd "${PORTAGE_BUILDDIR}"
	touch .tested || die "Failed to 'touch .tested' in ${PORTAGE_BUILDDIR}"
	[ "$(type -t post_src_test)" == "function" ] && qa_call post_src_test
	trap SIGINT SIGQUIT
}

dyn_install() {
	[ -z "$PORTAGE_BUILDDIR" ] && die "${FUNCNAME}: PORTAGE_BUILDDIR is unset"
	if hasq noauto $FEATURES ; then
		rm -f "${PORTAGE_BUILDDIR}/.installed"
	elif [[ ${PORTAGE_BUILDDIR}/.installed -nt ${WORKDIR} ]] ; then
		vecho ">>> It appears that '${PF}' is already installed; skipping."
		vecho ">>> Remove '${PORTAGE_BUILDDIR}/.installed' to force install."
		return 0
	fi
	trap "abort_install" SIGINT SIGQUIT
	[ "$(type -t pre_src_install)" == "function" ] && qa_call pre_src_install
	rm -rf "${PORTAGE_BUILDDIR}/image"
	mkdir "${PORTAGE_BUILDDIR}/image"
	if [ -d "${S}" ]; then
		cd "${S}"
	fi
	vecho
	vecho ">>> Install ${PF} into ${D} category ${CATEGORY}"
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages uses an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"
	qa_call src_install
	touch "${PORTAGE_BUILDDIR}/.installed"
	vecho ">>> Completed installing ${PF} into ${D}"
	vecho
	cd ${PORTAGE_BUILDDIR}
	[ "$(type -t post_src_install)" == "function" ] && qa_call post_src_install
	trap SIGINT SIGQUIT
}

dyn_preinst() {
	if [ -z "$IMAGE" ]; then
		eerror "${FUNCNAME}: IMAGE is unset"
		return 1
	fi

	[ "$(type -t pre_pkg_preinst)" == "function" ] && qa_call pre_pkg_preinst

	declare -r D=${IMAGE}
	pkg_preinst

	[ "$(type -t post_pkg_preinst)" == "function" ] && qa_call post_pkg_preinst
}

dyn_help() {
	echo
	echo "Portage"
	echo "Copyright 1999-2006 Gentoo Foundation"
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
	echo "  digest      : create a digest and a manifest file for the package"
	echo "  manifest    : create a manifest file for the package"
	echo "  unpack      : unpack/patch sources (auto-fetch if needed)"
	echo "  compile     : compile sources (auto-fetch/unpack if needed)"
	echo "  test        : test package (auto-fetch/unpack/compile if needed)"
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
	[ ! -d "$T" ] && return 0

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
	local olocation
	local PECLASS

	local B_IUSE
	local B_DEPEND
	local B_RDEPEND
	local B_PDEPEND
	while [ "$1" ]; do
		location="${ECLASSDIR}/${1}.eclass"
		olocation=""

		# PECLASS is used to restore the ECLASS var after recursion.
		PECLASS="$ECLASS"
		export ECLASS="$1"

		if [ "${EBUILD_PHASE}" != "depend" ] && \
			[[ ${EBUILD_PHASE} != *rm ]]; then
			# This is disabled in the *rm phases because they frequently give
			# false alarms due to INHERITED in /var/db/pkg being outdated
			# in comparison the the eclasses from the portage tree.
			if ! hasq $ECLASS $INHERITED; then
				eqawarn "QA Notice: ECLASS '$ECLASS' inherited illegally in $CATEGORY/$PF"
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
		unset B_IUSE B_DEPEND B_RDEPEND B_PDEPEND
		[ "${IUSE-unset}"    != "unset" ] && B_IUSE="${IUSE}"
		[ "${DEPEND-unset}"  != "unset" ] && B_DEPEND="${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && B_RDEPEND="${RDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && B_PDEPEND="${PDEPEND}"
		unset IUSE DEPEND RDEPEND PDEPEND
		#turn on glob expansion
		set +f

		qa_source "$location" || die "died sourcing $location in inherit()"
		
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
	((--ECLASS_DEPTH)) # Returns 1 when ECLASS_DEPTH reaches 0.
	return 0
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

if [[ ${EBUILD_SH_ARGS} != "depend" ]] && [[ ${EBUILD_SH_ARGS}  != "clean" ]] && [[ ${EBUILD_SH_ARGS} != "setup" ]]; then
	cd ${PORTAGE_TMPDIR} &> /dev/null
	cd ${BUILD_PREFIX} &> /dev/null

	if [ "$(id -nu)" == "portage" ] ; then
		export USER=portage
	fi

	if hasq distcc ${FEATURES} ; then
		if [ -d /usr/lib/distcc/bin ]; then
			#We can enable distributed compile support
			if [ -z "${PATH/*distcc*/}" ]; then
				# Remove the other reference.
				remove_path_entry "distcc"
			fi
			export PATH="/usr/lib/distcc/bin:${PATH}"
			[ ! -z "${DISTCC_LOG}" ] && addwrite "$(dirname ${DISTCC_LOG})"
		elif which distcc &>/dev/null; then
			if ! hasq distcc $CC; then
				export CC="distcc $CC"
			fi
			if ! hasq distcc $CXX; then
				export CXX="distcc $CXX"
			fi
		fi
	fi

	if hasq ccache ${FEATURES} ; then
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
	else
		# Force configure scripts that automatically detect ccache to respect
		# FEATURES="-ccache"
		export CCACHE_DISABLE=1
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

for x in T P PN PV PVR PR CATEGORY A EBUILD EMERGE_FROM O PPID FILESDIR PORTAGE_TMPDIR; do
	[[ ${!x-UNSET_VAR} != UNSET_VAR ]] && declare -r ${x}
done
# Need to be able to change D in dyn_preinst due to the IMAGE stuff
[[ ${EBUILD_SH_ARGS} != "preinst" ]] && declare -r D
unset x

# Turn of extended glob matching so that g++ doesn't get incorrectly matched.
shopt -u extglob

QA_INTERCEPTORS="javac java-config python python-config perl grep egrep fgrep sed gcc g++ cc bash awk nawk gawk pkg-config"
# level the QA interceptors if we're in depend
if hasq "depend" "${EBUILD_SH_ARGS}"; then
	for BIN in ${QA_INTERCEPTORS}; do
		BIN_PATH=$(type -Pf ${BIN})
		if [ "$?" != "0" ]; then
			BODY="echo \"*** missing command: ${BIN}\" >&2; return 127"
		else
			BODY="${BIN_PATH} \"\$@\"; return \$?"
		fi
		FUNC_SRC="${BIN}() {
		if [ \$ECLASS_DEPTH -gt 0 ]; then
			eqawarn \"QA Notice: '${BIN}' called in global scope: eclass \${ECLASS}\"
		else
			eqawarn \"QA Notice: '${BIN}' called in global scope: \${CATEGORY}/\${PF}\"
		fi
		${BODY}
		}";
		eval "$FUNC_SRC" || echo "error creating QA interceptor ${BIN}" >&2
	done
	unset BIN_PATH BIN BODY FUNC_SRC
fi

# reset the EBUILD_DEATH_HOOKS so they don't multiple due to stable's re-sourcing of env.
# this can be left out of ebd variants, since they're unaffected.
unset EBUILD_DEATH_HOOKS

# *DEPEND and IUSE will be set during the sourcing of the ebuild.  In order to
# ensure correct interaction between ebuilds and eclasses, they need to be
# unset before this process of interaction begins.
unset DEPEND RDEPEND PDEPEND IUSE

source ${EBUILD} || die "error sourcing ebuild"
if ! hasq depend $EBUILD_PHASE; then
	RESTRICT="${PORTAGE_RESTRICT}"
	unset PORTAGE_RESTRICT
fi

# Expand KEYWORDS
# We need to turn off pathname expansion for -* in KEYWORDS and
# we need to escape ~ to avoid tilde expansion
set -f
KEYWORDS=$(eval echo ${KEYWORDS//~/\\~})
set +f

if hasq nostrip ${FEATURES} ${RESTRICT} || hasq strip ${RESTRICT}
then
	export DEBUGBUILD=1
fi

#a reasonable default for $S
if [ "$S" = "" ]; then
	export S=${WORKDIR}/${P}
fi

#wipe the interceptors.  we don't want saved.
if hasq "depend" "${EBUILD_SH_ARGS}"; then
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
#syntax from getting expanded :)
#check eclass rdepends also.
set -f
if [ "${RDEPEND-unset}" == "unset" ] ; then
	export RDEPEND=${DEPEND}
	debug-print "RDEPEND: not set... Setting to: ${DEPEND}"
fi

#add in dependency info from eclasses
IUSE="$IUSE $E_IUSE"
DEPEND="$DEPEND $E_DEPEND"
RDEPEND="$RDEPEND $E_RDEPEND"
PDEPEND="$PDEPEND $E_PDEPEND"

unset E_IUSE E_DEPEND E_RDEPEND E_PDEPEND

if [ "${EBUILD_PHASE}" != "depend" ]; then
	# Make IUSE defaults backward compatible with all the old shell code.
	iuse_temp=""
	for x in ${IUSE} ; do
		if [[ ${x} == +* ]]; then
			iuse_temp="${iuse_temp} ${x:1}"
		else
			iuse_temp="${iuse_temp} ${x}"
		fi
	done
	export IUSE=${iuse_temp}
	unset iuse_temp
	# Lock the dbkey variables after the global phase
	declare -r DEPEND RDEPEND SLOT SRC_URI RESTRICT HOMEPAGE LICENSE DESCRIPTION
	declare -r KEYWORDS INHERITED IUSE PDEPEND PROVIDE
fi

set +f

for myarg in ${EBUILD_SH_ARGS} ; do
	case $myarg in
	nofetch)
		qa_call pkg_nofetch
		exit 1
		;;
	prerm|postrm|postinst|config)
		export SANDBOX_ON="0"
		if [ "$PORTAGE_DEBUG" != "1" ]; then
			[ "$(type -t pre_pkg_${myarg})" == "function" ] && qa_call pre_pkg_${myarg}
			qa_call pkg_${myarg}
			[ "$(type -t post_pkg_${myarg})" == "function" ] && qa_call post_pkg_${myarg}
			#Allow non-zero return codes since they can be caused by &&
		else
			set -x
			[ "$(type -t pre_pkg_${myarg})" == "function" ] && qa_call pre_pkg_${myarg}
			qa_call pkg_${myarg}
			[ "$(type -t post_pkg_${myarg})" == "function" ] && qa_call post_pkg_${myarg}
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
	help|setup|preinst)
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
			DESCRIPTION KEYWORDS INHERITED IUSE CDEPEND PDEPEND PROVIDE EAPI
			UNUSED_01 UNUSED_02 UNUSED_03 UNUSED_04 UNUSED_05 UNUSED_06
			UNUSED_07"

		#the extra $(echo) commands remove newlines
		unset CDEPEND
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
			9>&-
		fi
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

# Save the env only for relevant phases.
if [ -n "${myarg}" ] && \
	[ "${myarg}" != "clean" ] && \
	[ "${myarg}" != "help" ] ; then
	# Do not save myarg in the env, or else the above [ -n "$myarg" ] test will
	# give a false positive when ebuild.sh is sourced.
	unset myarg
	# Save current environment and touch a success file. (echo for success)
	umask 002
	set | egrep -v "^SANDBOX_" > "${T}/environment" 2>/dev/null
	export | egrep -v "^declare -x SANDBOX_" | \
		sed 's:^declare -rx:declare -x:' >> "${T}/environment" 2>/dev/null
	chown portage:portage "${T}/environment" &>/dev/null
	chmod g+w "${T}/environment" &>/dev/null
fi

# Do not exit when ebuild.sh is sourced by other scripts.
true
