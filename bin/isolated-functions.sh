#!/usr/bin/env bash
# Copyright 1999-2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
# shellcheck disable=2128,2185,2219

source "${PORTAGE_BIN_PATH:?}/eapi.sh" || exit

if ___eapi_has_ver_helpers; then
	source "${PORTAGE_BIN_PATH}/version-functions.sh" || exit 1
fi

if [[ -v PORTAGE_EBUILD_EXTRA_SOURCE ]]; then
	source "${PORTAGE_EBUILD_EXTRA_SOURCE}" || exit 1
	# We deliberately do not unset PORTAGE_EBUILD_EXTRA_SOURCE, so
	# that it keeps being exported in the environment of this
	# process and its child processes. There, for example portage
	# helper like doins, can pick it up and set the PMS variables
	# (usually by sourcing isolated-functions.sh).
fi

# We need this next line for "die" and "assert". It expands
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases

# Simplified version of pipestatus() for internal use
__pipestatus() {
	local status=( "${PIPESTATUS[@]}" ) s ret=0
	for s in "${status[@]}"; do
		[[ ${s} -ne 0 ]] && ret=${s}
	done
	return "${ret}"
}

shopt -s extdebug

# The client imports nothing from portage, so it needs neither PYTHONPATH
# nor a wrapper to set one up. It runs with -E so that a PYTHONPATH the
# ebuild exports cannot shadow the standard library, and with -X utf8 so
# that it does not re-exec itself for UTF-8 mode, which would drop -E.
__ebuild_ipc() {
	"${PORTAGE_PYTHON:-/usr/bin/python}" -E -S -X utf8 "${PORTAGE_BIN_PATH:?}/ebuild-ipc.py" "$@"
}

# Report the exit status of the phase to portage, on the pipe that it
# passes in, or with ebuild-ipc if it did not pass one.
__ebuild_exit() {
	if [[ -n ${PORTAGE_EBUILD_EXIT_FD} ]]; then
		printf '%s\n' "$1" >&${PORTAGE_EBUILD_EXIT_FD}
	else
		__ebuild_ipc exit "$1"
	fi
}

# __dump_trace([number of funcs on stack to skip],
#            [whitespacing for filenames],
#            [whitespacing for line numbers])
__dump_trace() {
	local strip=${1:-1} filespacing=$2 linespacing=$3
	local sourcefile funcname lineno n p

	# The __qa_call() function and anything before it are portage internals
	# that the user will not be interested in. Therefore, the stack trace
	# should only show calls that come after __qa_call().
	(( n = ${#FUNCNAME[@]} - 1 ))
	(( p = ${#BASH_ARGV[@]} ))
	while (( n > 0 )) ; do
		[[ "${FUNCNAME[${n}]}" == "__qa_call" ]] && break
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
		sourcefile="${BASH_SOURCE[${n}]}"
		sourcefile="${sourcefile##*/}"
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
		die "${FUNCNAME}() not supported in this EAPI"
	fi
	if [[ $# -lt 1 ]]; then
		die "${FUNCNAME}(): Missing argument"
	fi

	PORTAGE_NONFATAL=1 "$@"
}

__helpers_die() {
	local retval=$?

	if ___eapi_helpers_die_on_failure && [[ ${PORTAGE_NONFATAL} != 1 ]]; then
		die "$@"
	else
		echo -e "$@" >&2
		return "$(( retval ? retval : 1 ))"
	fi
}

die() {
	local retval=$?

	set +x # tracing only produces useless noise here
	local IFS=$' \t\n'
	# reset indentation when dying
	___state[einfo-indent]=""

	if ___eapi_die_supports_nonfatal && [[ $1 == -n ]]; then
		shift
		if [[ ${PORTAGE_NONFATAL} == 1 ]]; then
			[[ $# -gt 0 ]] && echo -e "$@" >&2
			return "$(( retval ? retval : 1 ))"
		fi
	fi

	set +e
	local n filespacing=0 linespacing=0
	# setup spacing to make output easier to read
	(( n = ${#FUNCNAME[@]} - 1 ))
	while (( n > 0 )) ; do
		[[ "${FUNCNAME[${n}]}" == "__qa_call" ]] && break
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
	[[ -n ${EBUILD_PHASE} ]] && phase_str=" (${EBUILD_PHASE} phase)"
	eerror "ERROR: ${CATEGORY}/${PF}::${PORTAGE_REPO_NAME} failed${phase_str}:"
	eerror "  ${*:-(no error message)}"
	eerror
	# __dump_trace is useless when the main script is a helper binary
	local main_index
	(( main_index = ${#BASH_SOURCE[@]} - 1 ))
	if [[ ${BASH_SOURCE[main_index]##*/} == @(ebuild|misc-functions).sh ]]; then
	__dump_trace 2 "${filespacing}" "${linespacing}"
	eerror "  $(printf "%${filespacing}s" "${BASH_SOURCE[1]##*/}"), line $(printf "%${linespacing}s" "${BASH_LINENO[0]}"):  Called die"
	eerror "The specific snippet of code:"
	# This scans the file that called die and prints out the logic that
	# ended in the call to die.  This really only handles lines that end
	# with '|| die' and any preceding lines with line continuations (\).
	# This tends to be the most common usage though, so let's do it.
	local -a lines
	mapfile -t -n "${BASH_LINENO[0]}" lines <"${BASH_SOURCE[1]}"
	# Loop backwards starting at the line preceding the target line,
	# until we encounter a line without continuation.
	(( n = ${#lines[@]} - 1 ))
	while (( --n >= 0 )) && [[ ${lines[n]} == *\\ ]]; do :; done
	while (( ++n < ${#lines[@]} )); do
		eerror "  ${lines[n]}"
	done
	eerror
	fi
	eerror "If you need support, post the output of \`emerge --info '=${CATEGORY}/${PF}::${PORTAGE_REPO_NAME}'\`,"
	eerror "the complete build log and the output of \`emerge -pqv '=${CATEGORY}/${PF}::${PORTAGE_REPO_NAME}'\`."

	# Only call die hooks here if we are executed via ebuild.sh or
	# misc-functions.sh, since those are the only cases where the environment
	# contains the hook functions. When necessary (like for __helpers_die), die
	# hooks are automatically called later by a misc-functions.sh invocation.
	if [[ ${EBUILD_PHASE} != depend && ${BASH_SOURCE[main_index]##*/} == @(ebuild|misc-functions).sh ]]
	then
		local x
		for x in ${EBUILD_DEATH_HOOKS}; do
			${x} "$@"
		done >&2
		: > "${PORTAGE_BUILDDIR}/.die_hooks"
	fi

	if [[ -n ${PORTAGE_LOG_FILE} ]] ; then
		eerror "The complete build log is located at '${PORTAGE_LOG_FILE}'."
		if [[ ${PORTAGE_LOG_FILE} != ${T}/* ]] \
			&& ! contains_word fail-clean "${FEATURES}"
		then
			# Display path to symlink in ${T}, as requested in bug #412865.
			local log_ext=log
			[[ ${PORTAGE_LOG_FILE} != *.log ]] && log_ext+=.${PORTAGE_LOG_FILE##*.}
			eerror "For convenience, a symlink to the build log is located at '${T}/build.${log_ext}'."
		fi
	fi
	if [[ -f "${T}/environment" ]]; then
		eerror "The ebuild environment file is located at '${T}/environment'."
	elif [[ -d "${T}" ]]; then
		{
			set
			export
		} > "${T}/die.env"
		eerror "The ebuild environment file is located at '${T}/die.env'."
	fi
	eerror "Working directory: '${PWD}'"
	[[ -n ${S} ]] && eerror "S: '${S}'"

	[[ -n ${PORTAGE_EBUILD_EXIT_FILE} ]] && : > "${PORTAGE_EBUILD_EXIT_FILE}"
	[[ -n ${PORTAGE_IPC_DAEMON} ]] && __ebuild_exit 1

	# subshell die support
	if [[ -n ${EBUILD_MASTER_PID} && ${BASHPID} != "${EBUILD_MASTER_PID}" ]] ; then
		kill -s SIGTERM "${EBUILD_MASTER_PID}"
	fi
	exit "$(( retval ? retval : 1 ))"
}

__quiet_mode() {
	[[ ${PORTAGE_QUIET} -eq 1 ]]
}

__vecho() {
	__quiet_mode || echo "$@" >&2
}

__elog_base() {
	local level=$1
	local line
	shift

	if [[ ${T} && -d ${T}/logging ]]; then
		for line; do
			printf '%s %s%s\n' "${level}" "${___state[einfo-indent]}" "${line%$'\n'}"
		done >> "${T}/logging/${EBUILD_PHASE:-other}"
	fi
}

__eprint() {
	local level=$1 format=$2
	local nameref color line msg IFS
	local -a lines
	shift 2

	if [[ ${EBUILD_PHASE} == depend ]] && (( ! ___state[banner-shown] )); then
		# If in the depend phase, output a banner indicating which
		# package emitted the message.
		printf '\nMessages for package %s%s%s:\n' \
			"${PORTAGE_COLOR_INFO}" "${CATEGORY}/${PF}::${PORTAGE_REPO_NAME}" "${PORTAGE_COLOR_NORMAL}"
		___state[banner-shown]=1
	fi

	case ${level} in
		QA)
			color=${PORTAGE_COLOR_QAWARN}
			;;
		ERROR)
			color=${PORTAGE_COLOR_ERR}
			;;
		*)
			nameref=PORTAGE_COLOR_${level}
			color=${!nameref}
	esac

	# As absurd as it is, PMS requires that <backslash>-escape sequences be
	# "interpreted as for the echo -e command of bash". Currently, callers
	# pass the %b format specifier to that end.
	#
	# https://projects.gentoo.org/pms/9/pms.html#x1-12700012.3.5
	# shellcheck disable=2059
	printf -v msg "${format}" "$*"

	# Read the message into an array of lines, each retaining its <newline>.
	# A here-string appends a <newline> of its own, so remove it from the
	# final element. Should that element then be empty, discard it unless it
	# is the only one, as occurs when einfon() is called without a message.
	if mapfile lines <<<"${msg}"; then
		lines[-1]=${lines[-1]%$'\n'}
		if [[ ! ${lines[-1]} ]] && (( ${#lines[@]} > 1 )); then
			unset -v 'lines[-1]'
		fi
	fi

	for line in "${lines[@]}"; do
		printf ' %s*%s %s%s' "${color}" "${PORTAGE_COLOR_NORMAL}" "${___state[einfo-indent]}" "${line}"
	done

	# Refrain from logging if the joined parameters form an empty string.
	# This is a historical quirk, for empty lines are otherwise logged.
	if (( $# > 1 || ${#1} > 0 )); then
		__elog_base "${level}" "${lines[@]}"
	fi
}

eqawarn() {
	__eprint >&2 QA '%b\n' "$@"
}

elog() {
	__eprint >&2 LOG '%b\n' "$@"
}

einfo() {
	__eprint >&2 INFO '%b\n' "$@"
}

einfon() {
	__eprint >&2 INFO '%b' "$@"
}

ewarn() {
	__eprint >&2 WARN '%b\n' "$@"
}

eerror() {
	__eprint >&2 ERROR '%b\n' "$@"
}

ebegin() {
	local msg

	msg="$* ..."
	einfon "${msg}"
	echo >&2
	(( ___state[ebegin-depth]++ ))
	return 0
}

__eend() {
	local retval=${1:-0} efunc=${2:-eerror}
	local columns msg
	shift 2

	if [[ ${retval} == "0" ]] ; then
		msg="${PORTAGE_COLOR_BRACKET}[ ${PORTAGE_COLOR_GOOD}ok${PORTAGE_COLOR_BRACKET} ]${PORTAGE_COLOR_NORMAL}"
	else
		if [[ -n $* ]] ; then
			${efunc} "$*"
		fi
		msg="${PORTAGE_COLOR_BRACKET}[ ${PORTAGE_COLOR_BAD}!!${PORTAGE_COLOR_BRACKET} ]${PORTAGE_COLOR_NORMAL}"
	fi

	if (( ___state[can-move-cursor] )); then
		# Move the cursor up by one line with CUU, then forward with CUF
		# to where the indicator belongs. This presumes that the ebegin
		# message occupied one line, and that the cursor is at the first
		# column, neither of which is guaranteed.
		columns=${| __get_columns; }
		printf '\e[A\e[%dC %b\n' "$(( columns > 8 ? columns - 8 : 0 ))" "${msg}" >&2
	else
		printf ' %b\n' "${msg}" >&2
	fi

	return "${retval}"
}

eend() {
	[[ -n ${1} ]] || die "${FUNCNAME}(): Missing argument"
	local retval=${1}
	shift
	if (( ___state[ebegin-depth]-- < 1 )); then
		___state[ebegin-depth]=0
		eqawarn "QA Notice: eend called without preceding ebegin in ${FUNCNAME[1]}"
	fi

	__eend "${retval}" eerror "$*"

	return "${retval}"
}

__unset_colors() {
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

# Determines whether the first parameter is an unsigned decimal integer.
# Leading zeroes are forbidden, lest they be considered as octal in an
# arithmetic context.
__is_uint() {
	[[ $1 == @(0|[1-9]*([0-9])) ]]
}

# Attempts to determine the width of the terminal presumed to be attached to
# standard error. The value of the COLUMNS variable shall be considered first,
# followed by the number of columns reported by the stty(1) utility. The first
# of these to be a positive integer shall be assigned to REPLY. If there is no
# such value, REPLY shall be assigned 80.
__get_columns() {
	local - IFS

	if __is_uint "${COLUMNS}" && (( COLUMNS > 0 )); then
		REPLY=${COLUMNS}
	else
		set -f
		# shellcheck disable=2046
		set -- $(stty size <&2 2>/dev/null)
		if __is_uint "$2" && (( $2 > 0 )); then
			REPLY=$2
		else
			REPLY=80
		fi
	fi
}

__set_colors() {
	# shellcheck disable=2034
	if [[ ${PORTAGE_COLORMAP} ]]; then
		# The PORTAGE_COLORMAP environment variable is defined by the
		# doebuild.py unit and is intended to be evaluated as code.
		eval "${PORTAGE_COLORMAP}"
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

# Declare the array where ebuild.sh has not, for the helpers source this unit
# but not ebuild.sh.
[[ ${___state@a} == *A* ]] || declare -A ___state=()

# Determines whether __eend() may move the cursor. It may not if colour is
# disabled, despite that being no indication of whether the terminal is able to.
___state[can-move-cursor]=1

___state[einfo-indent]=""

if [[ -z ${NO_COLOR} ]] ; then
	case ${NOCOLOR:-false} in
	yes|true)
		__unset_colors
		___state[can-move-cursor]=0
		;;
	no|false)
		__set_colors
		;;
	esac
else
	__unset_colors
	___state[can-move-cursor]=0
fi


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

# Assigns REPLY the number of jobs specified by the -j or --jobs option in
# MAKEOPTS or, failing that, the number of online processors. Should neither
# be determinable, assigns 1 and returns 1.
___makeopts_jobs() {
	local LC_ALL LC_COLLATE=C ere

	ere='.*[[:space:]](-[A-Ia-iK-Zk-z]*j[[:space:]]*|--jobs(=|[[:space:]]+))([0-9]+)[[:space:]]'

	if [[ " ${MAKEOPTS} " =~ $ere ]]; then
		REPLY=$(( 10#${BASH_REMATCH[3]} ))
	elif ! REPLY=${ { getconf _NPROCESSORS_ONLN || sysctl -n hw.ncpu; } 2>/dev/null; }; then
		REPLY=1
		false
	fi
}

# Considers the positional parameters as comprising a simple command, which
# shall be executed for each null-terminated record read from the standard
# input. For each record processed, its value shall be taken as an additional
# parameter to append to the command. Commands shall be executed in parallel,
# with the maximal degree of concurrency being determined by the
# ___makeopts_jobs() function. Thus, the behaviour is similar to that of
# xargs -0 -L1 -P"${| ___makeopts_jobs; }".
#
# If no records are read, or if all commands complete successfully, the return
# value shall be 0. Otherwise, the return value shall be that of the last
# reaped command that produced a non-zero exit status. As soon as any command
# fails, no further records shall be read, nor any further commands executed.
___parallel() (
	local max_procs retval arg i

	max_procs=${| ___makeopts_jobs; }
	retval=0

	while IFS= read -rd '' arg; do
		if (( i >= max_procs )); then
			wait -n
			case $? in
				0) (( i-- )) ;;
				*) retval=$?; (( i-- )); break
			esac
		fi
		"$@" "${arg}" & (( ++i ))
	done

	while (( i-- )); do
		wait -n
		case $? in
			0) ;;
			*) retval=$?
		esac
	done

	return "${retval}"
)

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

# Determines whether the first parameter is stringwise equal to any of the
# following parameters. Do NOT use this function for checking whether a word is
# contained by another string. For that, use contains_word() instead.
has() {
	local needle=$1
	shift

	local x
	for x in "$@"; do
		[[ "${x}" = "${needle}" ]] && return 0
	done
	return 1
}

__repo_attr() {
	local section key val i
	local -a records

	mapfile -td '' records < <(configparser <<<"${PORTAGE_REPOSITORIES}")

	for (( i = 0; i < ${#records[@]}; i += 3 )); do
		section=${records[i]}
		key=${records[i + 1]}
		if [[ ${section} == "$1" && ${key} == "$2" ]]; then
			val=${records[i + 2]}
			break
		fi
	done

	# Only print the found value in the case that configparser succeeded.
	wait "$!" && [[ -v val ]] && printf '%s\n' "${val}"
}

# __eqaquote <string>
#
# Assigns REPLY the value of the first parameter, with <backslash>,
# <quotation-mark> and <newline> escaped for inclusion in a
# double-quoted qa.log value.
__eqaquote() {
	REPLY=${1//\\/\\\\}
	REPLY=${REPLY//\"/\\\"}
	REPLY=${REPLY//$'\n'/\\n}
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
				echo "    ${i%%=*}: \"${| __eqaquote "${i#*=}"; }\""
			done
		fi
		if [[ ${#filenames[@]} -gt 0 ]]; then
			echo "  files:"
			for i in "${filenames[@]}"; do
				echo "    - \"${| __eqaquote "${i}"; }\""
			done
		fi
	) >> "${T}"/qa.log
}

# debug-print() gets called from many places with verbose status information useful
# for tracking down problems. The output is in ${T}/eclass-debug.log.
# You can set ECLASS_DEBUG_OUTPUT to redirect the output somewhere else as well.
# The special "on" setting echoes the information, mixing it with the rest of the
# emerge output.
# You can override the setting by exporting a new one from the console, or you can
# set a new default in make.*. Here the default is "" or unset.
#
# (TODO: in the future, might use e* from /lib/gentoo/functions.sh?)
debug-print() {
	# If ${T} isn't defined, we're in dep calculation mode and
	# shouldn't do anything
	[[ ${EBUILD_PHASE} = depend || ! -d ${T} || ${#} -eq 0 ]] && return 0

	if [[ ${ECLASS_DEBUG_OUTPUT} == on ]]; then
		printf 'debug: %s\n' "${@}" >&2
	elif [[ -n ${ECLASS_DEBUG_OUTPUT} ]]; then
		printf 'debug: %s\n' "${@}" >> "${ECLASS_DEBUG_OUTPUT}"
	fi

	if [[ -w ${T} ]] ; then
		# Default target
		printf '%s\n' "${@}" >> "${T}/eclass-debug.log"

		# Let the portage user own/write to this file
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

# Considers the first parameter as a word and the second parameter as a string
# comprising zero or more whitespace-separated words before determining whether
# said word can be matched against any of them. It addresses a use case for
# which the has() function is commonly misappropriated, with maximal efficiency.
contains_word() {
	local IFS
	[[ $1 == +([![:space:]]) && " ${*:2} " == *[[:space:]]"$1"[[:space:]]* ]]
}

# Invoke GNU find(1) in such a way that the paths to be searched are consumed
# as a list of one or more null-terminated records from STDIN. The positional
# parameters shall be conveyed verbatim and are guaranteed to be treated as
# options and/or primaries. This requires GNU findutils >=4.9.0.
find0() {
	find -files0-from - "$@"
}

# Consumes the standard input and attempts to parse it as the "configparser"
# configuration file format that is native to python. Each key/value entry
# shall be printed in the format of "%s\0%s\0%s\0", <section>, <key>, <value>.
# If the entirety of the input can be successfully parsed, the return value
# shall be 0. Otherwise, a diagnostic message shall be printed to standard
# error and the return value shall be greater than 0. Upon encountering the
# first error of syntax, no further key/value entries shall be printed.
configparser() {
	local IFS next_{section,key} reset_extglob scalar_val section flush key_i line key nr i
	local -a next_val lines val
	local -A seen

	reset_extglob=${ shopt -p extglob; }
	shopt -s extglob
	IFS=$'\n'

	# https://docs.python.org/3/library/configparser.html#supported-ini-file-structure
	mapfile -t lines
	for nr in "${!lines[@]}"; do
		# Trim trailing whitespace characters.
		line=${lines[nr++]%%+([[:space:]])}

		# Count and trim leading whitespace characters.
		[[ ${line} =~ ^[[:space:]]* ]]
		if (( i = ${#BASH_REMATCH} )); then
			line=${line:i}
		fi

		if [[ ${line} == [#\;]* ]]; then
			# Encountered a comment.
			false
		elif (( ${#val[@]} && (${#line} == 0 || i > key_i) )); then
			# Encountered the continuation of a multiline value.
			val+=( "${line}" )
			false
		elif (( ${#line} == 0 )); then
			# Encountered an empty line that is not a continuation.
			true
		elif [[ ${line} =~ ^\[(.+)\]$ ]]; then
			# Encountered a new section.
			next_section=${BASH_REMATCH[1]}
			seen=()
		elif [[ ${line} =~ ^([^:=]+)[:=][[:space:]]*(.*) ]]; then
			# Encountered the beginning of a key/value entry.
			next_key=${BASH_REMATCH[1]%%*([[:space:]])}
			if let 'seen[$next_key]++'; then
				printf >&2 \
					'configparser: duplicate key in section %s at STDIN[%d]: %s\n' \
					"${section@Q}" "${nr}" "${line@Q}"
				eval "${reset_extglob}"
				return 1
			elif [[ ! ${section} ]]; then
				printf >&2 \
					'configparser: key declared before section at STDIN[%d]: %s\n' \
					"${nr}" "${line@Q}"
				eval "${reset_extglob}"
				return 1
			fi
			next_val=( "${BASH_REMATCH[2]}" )
			key_i=$i
		else
			printf >&2 \
				'configparser: syntax error at STDIN[%d]: %s\n' \
				"${nr}" "${line@Q}"
			eval "${reset_extglob}"
			return 1
		fi && flush=1

		if (( nr == ${#lines[@]} - 1 )); then
			# Last line encountered. Flush any pending value.
			flush=1
		fi

		if (( flush && ${#val[@]} )); then
			# Print section, key and value, null-terminated.
			scalar_val=${val[*]}
			scalar_val=${scalar_val%%+($'\n')}
			printf '%s\0' "${section}" "${key}" "${scalar_val}"
			val=()
		fi

		section=${next_section}
		key=${next_key}
		if (( ${#next_val[@]} )); then
			val=( "${next_val[@]}" )
			next_val=()
		fi
		flush=0
	done

	eval "${reset_extglob}"
}

if ___eapi_has_eindent; then
	eindent() {
		___state[einfo-indent]+="  "
	}

	eoutdent() {
		if [[ ${#___state[einfo-indent]} -eq 0 ]]; then
			eqawarn "eoutdent called without eindent"
		fi
		___state[einfo-indent]=${___state[einfo-indent]%  }
	}
fi

true
