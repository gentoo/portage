#!/bin/bash
# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# We need this next line for "die" and "assert". It expands
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases
alias save_IFS='[ "${IFS:-unset}" != "unset" ] && old_IFS="${IFS}"'
alias restore_IFS='if [ "${old_IFS:-unset}" != "unset" ]; then IFS="${old_IFS}"; unset old_IFS; else unset IFS; fi'

assert() {
	local x pipestatus=${PIPESTATUS[*]}
	for x in $pipestatus ; do
		[[ $x -eq 0 ]] || die "$@"
	done
}

assert_sigpipe_ok() {
	# When extracting a tar file like this:
	#
	#     bzip2 -dc foo.tar.bz2 | tar xof -
	#
	# For some tar files (see bug #309001), tar will
	# close its stdin pipe when the decompressor still has
	# remaining data to be written to its stdout pipe. This
	# causes the decompressor to be killed by SIGPIPE. In
	# this case, we want to ignore pipe writers killed by
	# SIGPIPE, and trust the exit status of tar. We refer
	# to the bash manual section "3.7.5 Exit Status"
	# which says, "When a command terminates on a fatal
	# signal whose number is N, Bash uses the value 128+N
	# as the exit status."

	local x pipestatus=${PIPESTATUS[*]}
	for x in $pipestatus ; do
		# Allow SIGPIPE through (128 + 13)
		[[ $x -ne 0 && $x -ne ${PORTAGE_SIGPIPE_STATUS:-141} ]] && die "$@"
	done

	# Require normal success for the last process (tar).
	[[ $x -eq 0 ]] || die "$@"
}

shopt -s extdebug

# dump_trace([number of funcs on stack to skip],
#            [whitespacing for filenames],
#            [whitespacing for line numbers])
dump_trace() {
	local funcname="" sourcefile="" lineno="" s="yes" n p
	declare -i strip=${1:-1}
	local filespacing=$2 linespacing=$3

	# The qa_call() function and anything before it are portage internals
	# that the user will not be interested in. Therefore, the stack trace
	# should only show calls that come after qa_call().
	(( n = ${#FUNCNAME[@]} - 1 ))
	(( p = ${#BASH_ARGV[@]} ))
	while (( n > 0 )) ; do
		[ "${FUNCNAME[${n}]}" == "qa_call" ] && break
		(( p -= ${BASH_ARGC[${n}]} ))
		(( n-- ))
	done
	if (( n == 0 )) ; then
		(( n = ${#FUNCNAME[@]} - 1 ))
		(( p = ${#BASH_ARGV[@]} ))
	fi

	eerror "Call stack:"
	while (( n > ${strip} )) ; do
		funcname=${FUNCNAME[${n} - 1]}
		sourcefile=$(basename "${BASH_SOURCE[${n}]}")
		lineno=${BASH_LINENO[${n} - 1]}
		# Display function arguments
		args=
		if [[ -n "${BASH_ARGV[@]}" ]]; then
			for (( j = 1 ; j <= ${BASH_ARGC[${n} - 1]} ; ++j )); do
				newarg=${BASH_ARGV[$(( p - j - 1 ))]}
				args="${args:+${args} }'${newarg}'"
			done
			(( p -= ${BASH_ARGC[${n} - 1]} ))
		fi
		eerror "  $(printf "%${filespacing}s" "${sourcefile}"), line $(printf "%${linespacing}s" "${lineno}"):  Called ${funcname}${args:+ ${args}}"
		(( n-- ))
	done
}

nonfatal() {
	if has "${EAPI:-0}" 0 1 2 3 3_pre2 ; then
		die "$FUNCNAME() not supported in this EAPI"
	fi
	if [[ $# -lt 1 ]]; then
		die "$FUNCNAME(): Missing argument"
	fi

	PORTAGE_NONFATAL=1 "$@"
}

helpers_die() {
	case "${EAPI:-0}" in
		0|1|2|3)
			echo -e "$@" >&2
			;;
		*)
			die "$@"
			;;
	esac
}

die() {
	if [[ $PORTAGE_NONFATAL -eq 1 ]]; then
		echo -e " $WARN*$NORMAL ${FUNCNAME[1]}: WARNING: $@" >&2
		return 1
	fi

	set +e
	if [ -n "${QA_INTERCEPTORS}" ] ; then
		# die was called from inside inherit. We need to clean up
		# QA_INTERCEPTORS since sed is called below.
		unset -f ${QA_INTERCEPTORS}
		unset QA_INTERCEPTORS
	fi
	local n filespacing=0 linespacing=0
	# setup spacing to make output easier to read
	(( n = ${#FUNCNAME[@]} - 1 ))
	while (( n > 0 )) ; do
		[ "${FUNCNAME[${n}]}" == "qa_call" ] && break
		(( n-- ))
	done
	(( n == 0 )) && (( n = ${#FUNCNAME[@]} - 1 ))
	while (( n > 0 )); do
		sourcefile=${BASH_SOURCE[${n}]} sourcefile=${sourcefile##*/}
		lineno=${BASH_LINENO[${n}]}
		((filespacing < ${#sourcefile})) && filespacing=${#sourcefile}
		((linespacing < ${#lineno}))     && linespacing=${#lineno}
		(( n-- ))
	done

	# When a helper binary dies automatically in EAPI 4 and later, we don't
	# get a stack trace, so at least report the phase that failed.
	local phase_str=
	[[ -n $EBUILD_PHASE ]] && phase_str=" ($EBUILD_PHASE phase)"
	eerror "ERROR: $CATEGORY/$PF failed${phase_str}:"
	eerror "  ${*:-(no error message)}"
	eerror
	# dump_trace is useless when the main script is a helper binary
	local main_index
	(( main_index = ${#BASH_SOURCE[@]} - 1 ))
	if has ${BASH_SOURCE[$main_index]##*/} ebuild.sh misc-functions.sh ; then
	dump_trace 2 ${filespacing} ${linespacing}
	eerror "  $(printf "%${filespacing}s" "${BASH_SOURCE[1]##*/}"), line $(printf "%${linespacing}s" "${BASH_LINENO[0]}"):  Called die"
	eerror "The specific snippet of code:"
	# This scans the file that called die and prints out the logic that
	# ended in the call to die.  This really only handles lines that end
	# with '|| die' and any preceding lines with line continuations (\).
	# This tends to be the most common usage though, so let's do it.
	# Due to the usage of appending to the hold space (even when empty),
	# we always end up with the first line being a blank (thus the 2nd sed).
	sed -n \
		-e "# When we get to the line that failed, append it to the
		    # hold space, move the hold space to the pattern space,
		    # then print out the pattern space and quit immediately
		    ${BASH_LINENO[0]}{H;g;p;q}" \
		-e '# If this line ends with a line continuation, append it
		    # to the hold space
		    /\\$/H' \
		-e '# If this line does not end with a line continuation,
		    # erase the line and set the hold buffer to it (thus
		    # erasing the hold buffer in the process)
		    /[^\]$/{s:^.*$::;h}' \
		"${BASH_SOURCE[1]}" \
		| sed -e '1d' -e 's:^:RETAIN-LEADING-SPACE:' \
		| while read -r n ; do eerror "  ${n#RETAIN-LEADING-SPACE}" ; done
	eerror
	fi
	eerror "If you need support, post the output of 'emerge --info =$CATEGORY/$PF',"
	eerror "the complete build log and the output of 'emerge -pqv =$CATEGORY/$PF'."
	if [[ -n ${EBUILD_OVERLAY_ECLASSES} ]] ; then
		eerror "This ebuild used the following eclasses from overlays:"
		local x
		for x in ${EBUILD_OVERLAY_ECLASSES} ; do
			eerror "  ${x}"
		done
	fi
	if [ "${EMERGE_FROM}" != "binary" ] && \
		! hasq ${EBUILD_PHASE} prerm postrm && \
		[ "${EBUILD#${PORTDIR}/}" == "${EBUILD}" ] ; then
		local overlay=${EBUILD%/*}
		overlay=${overlay%/*}
		overlay=${overlay%/*}
		if [[ -n $PORTAGE_REPO_NAME ]] ; then
			eerror "This ebuild is from an overlay named" \
				"'$PORTAGE_REPO_NAME': '${overlay}/'"
		else
			eerror "This ebuild is from an overlay: '${overlay}/'"
		fi
	elif [[ -n $PORTAGE_REPO_NAME && -f "$PORTDIR"/profiles/repo_name ]] ; then
		local portdir_repo_name=$(<"$PORTDIR"/profiles/repo_name)
		if [[ -n $portdir_repo_name && \
			$portdir_repo_name != $PORTAGE_REPO_NAME ]] ; then
			eerror "This ebuild is from a repository" \
				"named '$PORTAGE_REPO_NAME'"
		fi
	fi

	if [[ "${EBUILD_PHASE/depend}" == "${EBUILD_PHASE}" ]] ; then
		local x
		for x in $EBUILD_DEATH_HOOKS; do
			${x} "$@" >&2 1>&2
		done
		> "$PORTAGE_BUILDDIR/.die_hooks"
	fi

	[[ -n ${PORTAGE_LOG_FILE} ]] \
		&& eerror "The complete build log is located at '${PORTAGE_LOG_FILE}'."
	if [ -f "${T}/environment" ] ; then
		eerror "The ebuild environment file is located at '${T}/environment'."
	elif [ -d "${T}" ] ; then
		{
			set
			export
		} > "${T}/die.env"
		eerror "The ebuild environment file is located at '${T}/die.env'."
	fi
	eerror "S: '${S}'"

	[[ -n $PORTAGE_EBUILD_EXIT_FILE ]] && > "$PORTAGE_EBUILD_EXIT_FILE"
	[[ -n $PORTAGE_IPC_DAEMON ]] && "$PORTAGE_BIN_PATH"/ebuild-ipc exit 1

	# subshell die support
	[[ $BASHPID = $EBUILD_MASTER_PID ]] || kill -s SIGTERM $EBUILD_MASTER_PID
	exit 1
}

# We need to implement diefunc() since environment.bz2 files contain
# calls to it (due to alias expansion).
diefunc() {
	die "${@}"
}

quiet_mode() {
	[[ ${PORTAGE_QUIET} -eq 1 ]]
}

vecho() {
	quiet_mode || echo "$@"
}

# Internal logging function, don't use this in ebuilds
elog_base() {
	local messagetype
	[ -z "${1}" -o -z "${T}" -o ! -d "${T}/logging" ] && return 1
	case "${1}" in
		INFO|WARN|ERROR|LOG|QA)
			messagetype="${1}"
			shift
			;;
		*)
			vecho -e " ${BAD}*${NORMAL} Invalid use of internal function elog_base(), next message will not be logged"
			return 1
			;;
	esac
	echo -e "$@" | while read -r ; do
		echo "$messagetype $REPLY" >> \
			"${T}/logging/${EBUILD_PHASE:-other}"
	done
	return 0
}

eqawarn() {
	elog_base QA "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e "$@" | while read -r ; do
		vecho " $WARN*$NORMAL $REPLY" >&2
	done
	LAST_E_CMD="eqawarn"
	return 0
}

elog() {
	elog_base LOG "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e "$@" | while read -r ; do
		echo " $GOOD*$NORMAL $REPLY"
	done
	LAST_E_CMD="elog"
	return 0
}

esyslog() {
	local pri=
	local tag=

	if [ -x /usr/bin/logger ]
	then
		pri="$1"
		tag="$2"

		shift 2
		[ -z "$*" ] && return 0

		/usr/bin/logger -p "${pri}" -t "${tag}" -- "$*"
	fi

	return 0
}

einfo() {
	elog_base INFO "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e "$@" | while read -r ; do
		echo " $GOOD*$NORMAL $REPLY"
	done
	LAST_E_CMD="einfo"
	return 0
}

einfon() {
	elog_base INFO "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -ne " ${GOOD}*${NORMAL} $*"
	LAST_E_CMD="einfon"
	return 0
}

ewarn() {
	elog_base WARN "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e "$@" | while read -r ; do
		echo " $WARN*$NORMAL $RC_INDENTATION$REPLY" >&2
	done
	LAST_E_CMD="ewarn"
	return 0
}

eerror() {
	elog_base ERROR "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e "$@" | while read -r ; do
		echo " $BAD*$NORMAL $RC_INDENTATION$REPLY" >&2
	done
	LAST_E_CMD="eerror"
	return 0
}

ebegin() {
	local msg="$*" dots spaces=${RC_DOT_PATTERN//?/ }
	if [[ -n ${RC_DOT_PATTERN} ]] ; then
		dots=$(printf "%$(( COLS - 3 - ${#RC_INDENTATION} - ${#msg} - 7 ))s" '')
		dots=${dots//${spaces}/${RC_DOT_PATTERN}}
		msg="${msg}${dots}"
	else
		msg="${msg} ..."
	fi
	einfon "${msg}"
	[[ ${RC_ENDCOL} == "yes" ]] && echo
	LAST_E_LEN=$(( 3 + ${#RC_INDENTATION} + ${#msg} ))
	LAST_E_CMD="ebegin"
	return 0
}

_eend() {
	local retval=${1:-0} efunc=${2:-eerror} msg
	shift 2

	if [[ ${retval} == "0" ]] ; then
		msg="${BRACKET}[ ${GOOD}ok${BRACKET} ]${NORMAL}"
	else
		if [[ -n $* ]] ; then
			${efunc} "$*"
		fi
		msg="${BRACKET}[ ${BAD}!!${BRACKET} ]${NORMAL}"
	fi

	if [[ ${RC_ENDCOL} == "yes" ]] ; then
		echo -e "${ENDCOL} ${msg}"
	else
		[[ ${LAST_E_CMD} == ebegin ]] || LAST_E_LEN=0
		printf "%$(( COLS - LAST_E_LEN - 7 ))s%b\n" '' "${msg}"
	fi

	return ${retval}
}

eend() {
	local retval=${1:-0}
	shift

	_eend ${retval} eerror "$*"

	LAST_E_CMD="eend"
	return ${retval}
}

KV_major() {
	[[ -z $1 ]] && return 1

	local KV=$@
	echo "${KV%%.*}"
}

KV_minor() {
	[[ -z $1 ]] && return 1

	local KV=$@
	KV=${KV#*.}
	echo "${KV%%.*}"
}

KV_micro() {
	[[ -z $1 ]] && return 1

	local KV=$@
	KV=${KV#*.*.}
	echo "${KV%%[^[:digit:]]*}"
}

KV_to_int() {
	[[ -z $1 ]] && return 1

	local KV_MAJOR=$(KV_major "$1")
	local KV_MINOR=$(KV_minor "$1")
	local KV_MICRO=$(KV_micro "$1")
	local KV_int=$(( KV_MAJOR * 65536 + KV_MINOR * 256 + KV_MICRO ))

	# We make version 2.2.0 the minimum version we will handle as
	# a sanity check ... if its less, we fail ...
	if [[ ${KV_int} -ge 131584 ]] ; then
		echo "${KV_int}"
		return 0
	fi

	return 1
}

_RC_GET_KV_CACHE=""
get_KV() {
	[[ -z ${_RC_GET_KV_CACHE} ]] \
		&& _RC_GET_KV_CACHE=$(uname -r)

	echo $(KV_to_int "${_RC_GET_KV_CACHE}")

	return $?
}

unset_colors() {
	COLS=80
	ENDCOL=

	GOOD=
	WARN=
	BAD=
	NORMAL=
	HILITE=
	BRACKET=
}

set_colors() {
	COLS=${COLUMNS:-0}      # bash's internal COLUMNS variable
	(( COLS == 0 )) && COLS=$(set -- $(stty size 2>/dev/null) ; echo $2)
	(( COLS > 0 )) || (( COLS = 80 ))

	# Now, ${ENDCOL} will move us to the end of the
	# column;  irregardless of character width
	ENDCOL=$'\e[A\e['$(( COLS - 8 ))'C'
	if [ -n "${PORTAGE_COLORMAP}" ] ; then
		eval ${PORTAGE_COLORMAP}
	else
		GOOD=$'\e[32;01m'
		WARN=$'\e[33;01m'
		BAD=$'\e[31;01m'
		HILITE=$'\e[36;01m'
		BRACKET=$'\e[34;01m'
	fi
	NORMAL=$'\e[0m'
}

RC_ENDCOL="yes"
RC_INDENTATION=''
RC_DEFAULT_INDENT=2
RC_DOT_PATTERN=''

case "${NOCOLOR:-false}" in
	yes|true)
		unset_colors
		;;
	no|false)
		set_colors
		;;
esac

if [[ -z ${USERLAND} ]] ; then
	case $(uname -s) in
	*BSD|DragonFly)
		export USERLAND="BSD"
		;;
	*)
		export USERLAND="GNU"
		;;
	esac
fi

if [[ -z ${XARGS} ]] ; then
	case ${USERLAND} in
	BSD)
		export XARGS="xargs"
		;;
	*)
		export XARGS="xargs -r"
		;;
	esac
fi

has() {
	hasq "$@"
}

hasv() {
	if hasq "$@" ; then
		echo "$1"
		return 0
	fi
	return 1
}

hasq() {
	[[ " ${*:2} " == *" $1 "* ]]
}

# @FUNCTION: save_ebuild_env
# @DESCRIPTION:
# echo the current environment to stdout, filtering out redundant info.
#
# --exclude-init-phases causes pkg_nofetch and src_* phase functions to
# be excluded from the output. These function are not needed for installation
# or removal of the packages, and can therefore be safely excluded.
#
save_ebuild_env() {
	(

		if hasq --exclude-init-phases $* ; then
			unset S _E_DOCDESTTREE_ _E_EXEDESTTREE_
			if [[ -n $PYTHONPATH ]] ; then
				export PYTHONPATH=${PYTHONPATH/${PORTAGE_PYM_PATH}:}
				[[ -z $PYTHONPATH ]] && unset PYTHONPATH
			fi
		fi

		# misc variables inherited from the calling environment
		unset COLORTERM DISPLAY EDITOR LESS LESSOPEN LOGNAME LS_COLORS PAGER \
			TERM TERMCAP USER ftp_proxy http_proxy no_proxy

		# other variables inherited from the calling environment
		unset CVS_RSH ECHANGELOG_USER GPG_AGENT_INFO \
		SSH_AGENT_PID SSH_AUTH_SOCK STY WINDOW XAUTHORITY

		# CCACHE and DISTCC config
		unset ${!CCACHE_*} ${!DISTCC_*}

		# There's no need to bloat environment.bz2 with internally defined
		# functions and variables, so filter them out if possible.

		for x in pkg_setup pkg_nofetch src_unpack src_prepare src_configure \
			src_compile src_test src_install pkg_preinst pkg_postinst \
			pkg_prerm pkg_postrm ; do
			unset -f default_$x _eapi{0,1,2,3,4}_$x
		done
		unset x

		unset -f assert assert_sigpipe_ok dump_trace die diefunc \
			quiet_mode vecho elog_base eqawarn elog \
			esyslog einfo einfon ewarn eerror ebegin _eend eend KV_major \
			KV_minor KV_micro KV_to_int get_KV unset_colors set_colors has \
			has_phase_defined_up_to \
			hasg hasgq hasv hasq qa_source qa_call \
			addread addwrite adddeny addpredict _sb_append_var \
			lchown lchgrp esyslog use usev useq has_version portageq \
			best_version use_with use_enable register_die_hook \
			keepdir unpack strip_duplicate_slashes econf einstall \
			dyn_setup dyn_unpack dyn_clean into insinto exeinto docinto \
			insopts diropts exeopts libopts docompress \
			abort_handler abort_prepare abort_configure abort_compile \
			abort_test abort_install dyn_prepare dyn_configure \
			dyn_compile dyn_test dyn_install \
			dyn_preinst dyn_help debug-print debug-print-function \
			debug-print-section inherit EXPORT_FUNCTIONS remove_path_entry \
			save_ebuild_env filter_readonly_variables preprocess_ebuild_env \
			source_all_bashrcs ebuild_main \
			ebuild_phase ebuild_phase_with_hooks \
			_ebuild_arg_to_phase _ebuild_phase_funcs default \
			_pipestatus \
			${QA_INTERCEPTORS}

		# portage config variables and variables set directly by portage
		unset ACCEPT_LICENSE BAD BRACKET BUILD_PREFIX COLS \
			DISTCC_DIR DISTDIR DOC_SYMLINKS_DIR \
			EBUILD_FORCE_TEST EBUILD_MASTER_PID \
			ECLASS_DEPTH ENDCOL FAKEROOTKEY \
			GOOD HILITE HOME \
			LAST_E_CMD LAST_E_LEN LD_PRELOAD MISC_FUNCTIONS_ARGS MOPREFIX \
			NOCOLOR NORMAL PKGDIR PKGUSE PKG_LOGDIR PKG_TMPDIR \
			PORTAGE_BASHRCS_SOURCED PORTAGE_NONFATAL PORTAGE_QUIET \
			PORTAGE_SANDBOX_DENY PORTAGE_SANDBOX_PREDICT \
			PORTAGE_SANDBOX_READ PORTAGE_SANDBOX_WRITE PREROOTPATH \
			QA_INTERCEPTORS \
			RC_DEFAULT_INDENT RC_DOT_PATTERN RC_ENDCOL RC_INDENTATION  \
			ROOT ROOTPATH RPMDIR TEMP TMP TMPDIR USE_EXPAND \
			WARN XARGS _RC_GET_KV_CACHE

		# user config variables
		unset DOC_SYMLINKS_DIR INSTALL_MASK PKG_INSTALL_MASK

		declare -p
		declare -fp
		if [[ ${BASH_VERSINFO[0]} == 3 ]]; then
			export
		fi
	)
}

true
