#!/bin/bash
# Copyright 1999-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

source "${PORTAGE_BIN_PATH}/eapi.sh" || exit 1

if ___eapi_has_version_functions; then
	source "${PORTAGE_BIN_PATH}/eapi7-ver-funcs.sh" || exit 1
fi

# We need this next line for "die" and "assert". It expands
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases

assert() {
	local x pipestatus=${PIPESTATUS[*]}
	for x in $pipestatus ; do
		[[ $x -eq 0 ]] || die "$@"
	done
}

__assert_sigpipe_ok() {
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

# __dump_trace([number of funcs on stack to skip],
#            [whitespacing for filenames],
#            [whitespacing for line numbers])
__dump_trace() {
	local funcname="" sourcefile="" lineno="" s="yes" n p
	declare -i strip=${1:-1}
	local filespacing=$2 linespacing=$3

	# The __qa_call() function and anything before it are portage internals
	# that the user will not be interested in. Therefore, the stack trace
	# should only show calls that come after __qa_call().
	(( n = ${#FUNCNAME[@]} - 1 ))
	(( p = ${#BASH_ARGV[@]} ))
	while (( n > 0 )) ; do
		[ "${FUNCNAME[${n}]}" == "__qa_call" ] && break
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
		if [[ ${#BASH_ARGV[@]} -gt 0 ]]; then
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
	if ! ___eapi_has_nonfatal; then
		die "$FUNCNAME() not supported in this EAPI"
	fi
	if [[ $# -lt 1 ]]; then
		die "$FUNCNAME(): Missing argument"
	fi

	PORTAGE_NONFATAL=1 "$@"
}

__bashpid() {
	# The BASHPID variable is new to bash-4.0, so add a hack for older
	# versions.  This must be used like so:
	# ${BASHPID:-$(__bashpid)}
	sh -c 'echo ${PPID}'
}

__helpers_die() {
	if ___eapi_helpers_can_die && [[ ${PORTAGE_NONFATAL} != 1 ]]; then
		die "$@"
	else
		echo -e "$@" >&2
	fi
}

die() {
	# restore PATH since die calls basename & sed
	# TODO: make it pure bash
	[[ -n ${_PORTAGE_ORIG_PATH} ]] && PATH=${_PORTAGE_ORIG_PATH}

	set +x # tracing only produces useless noise here
	local IFS=$' \t\n'

	if ___eapi_die_can_respect_nonfatal && [[ $1 == -n ]]; then
		shift
		if [[ ${PORTAGE_NONFATAL} == 1 ]]; then
			[[ $# -gt 0 ]] && eerror "$*"
			return 1
		fi
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
		[ "${FUNCNAME[${n}]}" == "__qa_call" ] && break
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
	eerror "ERROR: ${CATEGORY}/${PF}::${PORTAGE_REPO_NAME} failed${phase_str}:"
	eerror "  ${*:-(no error message)}"
	eerror
	# __dump_trace is useless when the main script is a helper binary
	local main_index
	(( main_index = ${#BASH_SOURCE[@]} - 1 ))
	if has ${BASH_SOURCE[$main_index]##*/} ebuild.sh misc-functions.sh ; then
	__dump_trace 2 ${filespacing} ${linespacing}
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
	eerror "If you need support, post the output of \`emerge --info '=${CATEGORY}/${PF}::${PORTAGE_REPO_NAME}'\`,"
	eerror "the complete build log and the output of \`emerge -pqv '=${CATEGORY}/${PF}::${PORTAGE_REPO_NAME}'\`."

	# Only call die hooks here if we are executed via ebuild.sh or
	# misc-functions.sh, since those are the only cases where the environment
	# contains the hook functions. When necessary (like for __helpers_die), die
	# hooks are automatically called later by a misc-functions.sh invocation.
	if has ${BASH_SOURCE[$main_index]##*/} ebuild.sh misc-functions.sh && \
		[[ ${EBUILD_PHASE} != depend ]] ; then
		local x
		for x in $EBUILD_DEATH_HOOKS; do
			${x} "$@" >&2 1>&2
		done
		> "$PORTAGE_BUILDDIR/.die_hooks"
	fi

	if [[ -n ${PORTAGE_LOG_FILE} ]] ; then
		eerror "The complete build log is located at '${PORTAGE_LOG_FILE}'."
		if [[ ${PORTAGE_LOG_FILE} != ${T}/* ]] && \
			! has fail-clean ${FEATURES} ; then
			# Display path to symlink in ${T}, as requested in bug #412865.
			local log_ext=log
			[[ ${PORTAGE_LOG_FILE} != *.log ]] && log_ext+=.${PORTAGE_LOG_FILE##*.}
			eerror "For convenience, a symlink to the build log is located at '${T}/build.${log_ext}'."
		fi
	fi
	if [ -f "${T}/environment" ] ; then
		eerror "The ebuild environment file is located at '${T}/environment'."
	elif [ -d "${T}" ] ; then
		{
			set
			export
		} > "${T}/die.env"
		eerror "The ebuild environment file is located at '${T}/die.env'."
	fi
	eerror "Working directory: '$(pwd)'"
	eerror "S: '${S}'"

	[[ -n $PORTAGE_EBUILD_EXIT_FILE ]] && > "$PORTAGE_EBUILD_EXIT_FILE"
	[[ -n $PORTAGE_IPC_DAEMON ]] && "$PORTAGE_BIN_PATH"/ebuild-ipc exit 1

	# subshell die support
	[[ ${BASHPID:-$(__bashpid)} == ${EBUILD_MASTER_PID} ]] || kill -s SIGTERM ${EBUILD_MASTER_PID}
	exit 1
}

__quiet_mode() {
	[[ ${PORTAGE_QUIET} -eq 1 ]]
}

__vecho() {
	__quiet_mode || echo "$@" >&2
}

# Internal logging function, don't use this in ebuilds
__elog_base() {
	local messagetype
	[ -z "${1}" -o -z "${T}" -o ! -d "${T}/logging" ] && return 1
	case "${1}" in
		INFO|WARN|ERROR|LOG|QA)
			messagetype="${1}"
			shift
			;;
		*)
			__vecho -e " ${PORTAGE_COLOR_BAD}*${PORTAGE_COLOR_NORMAL} Invalid use of internal function __elog_base(), next message will not be logged"
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
	__elog_base QA "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo >&2
	echo -e "$@" | while read -r ; do
		echo " ${PORTAGE_COLOR_QAWARN}*${PORTAGE_COLOR_NORMAL} ${REPLY}" >&2
	done
	LAST_E_CMD="eqawarn"
	return 0
}

elog() {
	__elog_base LOG "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo >&2
	echo -e "$@" | while read -r ; do
		echo " ${PORTAGE_COLOR_LOG}*${PORTAGE_COLOR_NORMAL} ${REPLY}" >&2
	done
	LAST_E_CMD="elog"
	return 0
}

einfo() {
	__elog_base INFO "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo >&2
	echo -e "$@" | while read -r ; do
		echo " ${PORTAGE_COLOR_INFO}*${PORTAGE_COLOR_NORMAL} ${REPLY}" >&2
	done
	LAST_E_CMD="einfo"
	return 0
}

einfon() {
	__elog_base INFO "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo >&2
	echo -ne " ${PORTAGE_COLOR_INFO}*${PORTAGE_COLOR_NORMAL} $*" >&2
	LAST_E_CMD="einfon"
	return 0
}

ewarn() {
	__elog_base WARN "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo >&2
	echo -e "$@" | while read -r ; do
		echo " ${PORTAGE_COLOR_WARN}*${PORTAGE_COLOR_NORMAL} ${RC_INDENTATION}${REPLY}" >&2
	done
	LAST_E_CMD="ewarn"
	return 0
}

eerror() {
	__elog_base ERROR "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo >&2
	echo -e "$@" | while read -r ; do
		echo " ${PORTAGE_COLOR_ERR}*${PORTAGE_COLOR_NORMAL} ${RC_INDENTATION}${REPLY}" >&2
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
	[[ ${RC_ENDCOL} == "yes" ]] && echo >&2
	LAST_E_LEN=$(( 3 + ${#RC_INDENTATION} + ${#msg} ))
	LAST_E_CMD="ebegin"
	return 0
}

__eend() {
	local retval=${1:-0} efunc=${2:-eerror} msg
	shift 2

	if [[ ${retval} == "0" ]] ; then
		msg="${PORTAGE_COLOR_BRACKET}[ ${PORTAGE_COLOR_GOOD}ok${PORTAGE_COLOR_BRACKET} ]${PORTAGE_COLOR_NORMAL}"
	else
		if [[ -n $* ]] ; then
			${efunc} "$*"
		fi
		msg="${PORTAGE_COLOR_BRACKET}[ ${PORTAGE_COLOR_BAD}!!${PORTAGE_COLOR_BRACKET} ]${PORTAGE_COLOR_NORMAL}"
	fi

	if [[ ${RC_ENDCOL} == "yes" ]] ; then
		echo -e "${ENDCOL} ${msg}" >&2
	else
		[[ ${LAST_E_CMD} == ebegin ]] || LAST_E_LEN=0
		printf "%$(( COLS - LAST_E_LEN - 7 ))s%b\n" '' "${msg}" >&2
	fi

	return ${retval}
}

eend() {
	[[ -n $1 ]] || eqawarn "QA Notice: eend called without first argument"
	local retval=${1:-0}
	shift

	__eend ${retval} eerror "$*"

	LAST_E_CMD="eend"
	return ${retval}
}

__unset_colors() {
	COLS=80
	ENDCOL=

	PORTAGE_COLOR_BAD=
	PORTAGE_COLOR_BRACKET=
	PORTAGE_COLOR_ERR=
	PORTAGE_COLOR_GOOD=
	PORTAGE_COLOR_HILITE=
	PORTAGE_COLOR_INFO=
	PORTAGE_COLOR_LOG=
	PORTAGE_COLOR_NORMAL=
	PORTAGE_COLOR_QAWARN=
	PORTAGE_COLOR_WARN=
}

__set_colors() {
	COLS=${COLUMNS:-0}      # bash's internal COLUMNS variable
	# Avoid wasteful stty calls during the "depend" phases.
	# If stdout is a pipe, the parent process can export COLUMNS
	# if it's relevant. Use an extra subshell for stty calls, in
	# order to redirect "/dev/tty: No such device or address"
	# error from bash to /dev/null.
	[[ $COLS == 0 && $EBUILD_PHASE != depend ]] && \
		COLS=$(set -- $( ( stty size </dev/tty ) 2>/dev/null || echo 24 80 ) ; echo $2)
	(( COLS > 0 )) || (( COLS = 80 ))

	# Now, ${ENDCOL} will move us to the end of the
	# column;  irregardless of character width
	ENDCOL=$'\e[A\e['$(( COLS - 8 ))'C'
	if [ -n "${PORTAGE_COLORMAP}" ] ; then
		eval ${PORTAGE_COLORMAP}
	else
		PORTAGE_COLOR_BAD=$'\e[31;01m'
		PORTAGE_COLOR_BRACKET=$'\e[34;01m'
		PORTAGE_COLOR_ERR=$'\e[31;01m'
		PORTAGE_COLOR_GOOD=$'\e[32;01m'
		PORTAGE_COLOR_HILITE=$'\e[36;01m'
		PORTAGE_COLOR_INFO=$'\e[32m'
		PORTAGE_COLOR_LOG=$'\e[32;01m'
		PORTAGE_COLOR_NORMAL=$'\e[0m'
		PORTAGE_COLOR_QAWARN=$'\e[33m'
		PORTAGE_COLOR_WARN=$'\e[33;01m'
	fi
}

RC_ENDCOL="yes"
RC_INDENTATION=''
RC_DEFAULT_INDENT=2
RC_DOT_PATTERN=''

case "${NOCOLOR:-false}" in
	yes|true)
		__unset_colors
		;;
	no|false)
		__set_colors
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
		if type -P gxargs > /dev/null; then
			export XARGS="gxargs -r"
		else
			export XARGS="xargs"
		fi
		;;
	*)
		export XARGS="xargs -r"
		;;
	esac
fi

___makeopts_jobs() {
	# Copied from eutils.eclass:makeopts_jobs()
	local jobs
	jobs=$(echo " ${MAKEOPTS} " | \
		sed -r -n 's:.*[[:space:]](-j|--jobs[=[:space:]])[[:space:]]*([0-9]+).*:\2:p') || die
	echo ${jobs:-1}
}

# Run ${XARGS} in parallel for detected number of CPUs, if supported.
# Passes all arguments to xargs, and returns its exit code
___parallel_xargs() {
	local chunksize=1 jobs xargs=( ${XARGS} )

	if "${xargs[@]}" --help | grep -q -- --max-procs=; then
		jobs=$(___makeopts_jobs)
		if [[ ${jobs} -gt 1 ]]; then
			xargs+=("--max-procs=${jobs}" -L "${chunksize}")
		fi
	fi

	"${xargs[@]}" "${@}"
}

hasq() {
	___eapi_has_hasq || die "'${FUNCNAME}' banned in EAPI ${EAPI}"

	eqawarn "QA Notice: The 'hasq' function is deprecated (replaced by 'has')"
	has "$@"
}

hasv() {
	___eapi_has_hasv || die "'${FUNCNAME}' banned in EAPI ${EAPI}"

	if has "$@" ; then
		echo "$1"
		return 0
	fi
	return 1
}

has() {
	local needle=$1
	shift

	local x
	for x in "$@"; do
		[ "${x}" = "${needle}" ] && return 0
	done
	return 1
}

__repo_attr() {
	local appropriate_section=0 exit_status=1 line saved_extglob_shopt=$(shopt -p extglob)
	shopt -s extglob
	while read line; do
		[[ ${appropriate_section} == 0 && ${line} == "[$1]" ]] && appropriate_section=1 && continue
		[[ ${appropriate_section} == 1 && ${line} == "["*"]" ]] && appropriate_section=0 && continue
		# If a conditional expression like [[ ${line} == $2*( )=* ]] is used
		# then bash-3.2 produces an error like the following when the file is
		# sourced: syntax error in conditional expression: unexpected token `('
		# Therefore, use a regular expression for compatibility.
		if [[ ${appropriate_section} == 1 && ${line} =~ ^${2}[[:space:]]*= ]]; then
			echo "${line##$2*( )=*( )}"
			exit_status=0
			break
		fi
	done <<< "${PORTAGE_REPOSITORIES}"
	eval "${saved_extglob_shopt}"
	return ${exit_status}
}

# eqaquote <string>
#
# outputs parameter escaped for quoting
__eqaquote() {
	local v=${1} esc=''

	# quote backslashes
	v=${v//\\/\\\\}
	# quote the quotes
	v=${v//\"/\\\"}
	# quote newlines
	while read -r; do
		echo -n "${esc}${REPLY}"
		esc='\n'
	done <<<"${v}"
}

# eqatag <tag> [-v] [<key>=<value>...] [/<relative-path>...]
#
# output (to qa.log):
# - tag: <tag>
#   data:
#     <key1>: "<value1>"
#     <key2>: "<value2>"
#   files:
#     - "<path1>"
#     - "<path2>"
__eqatag() {
	local tag i filenames=() data=() verbose=

	if [[ ${1} == -v ]]; then
		verbose=1
		shift
	fi

	tag=${1}
	shift
	[[ -n ${tag} ]] || die "${FUNCNAME}: no tag specified"

	# collect data & filenames
	for i; do
		if [[ ${i} == /* ]]; then
			filenames+=( "${i}" )
			[[ -n ${verbose} ]] && eqawarn "  ${i}"
		elif [[ ${i} == *=* ]]; then
			data+=( "${i}" )
		else
			die "${FUNCNAME}: invalid parameter: ${i}"
		fi
	done

	(
		echo "- tag: ${tag}"
		if [[ ${#data[@]} -gt 0 ]]; then
			echo "  data:"
			for i in "${data[@]}"; do
				echo "    ${i%%=*}: \"$(__eqaquote "${i#*=}")\""
			done
		fi
		if [[ ${#filenames[@]} -gt 0 ]]; then
			echo "  files:"
			for i in "${filenames[@]}"; do
				echo "    - \"$(__eqaquote "${i}")\""
			done
		fi
	) >> "${T}"/qa.log
}

if [[ BASH_VERSINFO -gt 4 || (BASH_VERSINFO -eq 4 && BASH_VERSINFO[1] -ge 4) ]] ; then
	___is_indexed_array_var() {
		[[ ${!1@a} == *a* ]]
	}
else
	___is_indexed_array_var() {
		[[ $(declare -p "$1" 2>/dev/null) == 'declare -a'* ]]
	}
fi

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
		chgrp "${PORTAGE_GRPNAME:-portage}" "${T}/eclass-debug.log"
		chmod g+w "${T}/eclass-debug.log"
	fi
}

# The following 2 functions are debug-print() wrappers

debug-print-function() {
	debug-print "${1}: entering function, parameters: ${*:2}"
}

debug-print-section() {
	debug-print "now in section ${*}"
}

true
