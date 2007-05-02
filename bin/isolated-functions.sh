# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

# We need this next line for "die" and "assert". It expands
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases
alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
alias assert='_pipestatus="${PIPESTATUS[*]}"; [[ "${_pipestatus// /}" -eq 0 ]] || diefunc "$FUNCNAME" "$LINENO" "$_pipestatus"'
alias save_IFS='[ "${IFS:-unset}" != "unset" ] && old_IFS="${IFS}"'
alias restore_IFS='if [ "${old_IFS:-unset}" != "unset" ]; then IFS="${old_IFS}"; unset old_IFS; else unset IFS; fi'

shopt -s extdebug

# usage- first arg is the number of funcs on the stack to ignore.
# defaults to 1 (ignoring dump_trace)
dump_trace() {
        local funcname="" sourcefile="" lineno="" n e s="yes"

        declare -i strip=1

        if [[ -n $1 ]]; then
                strip=$(( $1 ))
        fi

        echo "Call stack:"
        for (( n = ${#FUNCNAME[@]} - 1, p = ${#BASH_ARGV[@]} ; n > $strip ; n-- )) ; do
                funcname=${FUNCNAME[${n} - 1]}
                sourcefile=$(basename ${BASH_SOURCE[${n}]})
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
                echo "  ${sourcefile}, line ${lineno}:   Called ${funcname}${args:+ ${args}}"
        done
}

diefunc() {
        local funcname="$1" lineno="$2" exitcode="$3"
        shift 3
        echo >&2
        echo "!!! ERROR: $CATEGORY/$PF failed." >&2
        dump_trace 2 1>&2
        echo "  $(basename "${BASH_SOURCE[1]}"), line ${BASH_LINENO[0]}:   Called die" 1>&2
        echo >&2
        echo "!!! ${*:-(no error message)}" >&2
        echo "!!! If you need support, post the topmost build error, and the call stack if relevant." >&2
        [ -n "${PORTAGE_LOG_FILE}" ] && \
            echo "!!! A complete build log is located at '${PORTAGE_LOG_FILE}'." >&2
        echo >&2
        if [ -n "${EBUILD_OVERLAY_ECLASSES}" ] ; then
                echo "This ebuild used the following eclasses from overlays:" >&2
                echo >&2
                for x in ${EBUILD_OVERLAY_ECLASSES} ; do
                        echo "  ${x}" >&2
                done
                echo >&2
        fi

        if [ "${EBUILD_PHASE/depend}" == "${EBUILD_PHASE}" ]; then
                local x
                for x in $EBUILD_DEATH_HOOKS; do
                        ${x} "$@" >&2 1>&2
                done
        fi

        # subshell die support
        kill -s SIGTERM ${EBUILD_MASTER_PID}
        exit 1
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
	echo -e "$*" >> ${T}/logging/${EBUILD_PHASE:-other}.${messagetype}
	return 0
}

eqawarn() {
	elog_base QA "$*"
	vecho -e " ${WARN}*${NORMAL} $*" >&2
	return 0
}

elog() {
	elog_base LOG "$*"
	echo -e " ${GOOD}*${NORMAL} $*"
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
	echo -e " ${GOOD}*${NORMAL} $*"
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
	echo -e " ${WARN}*${NORMAL} ${RC_INDENTATION}$*"
	LAST_E_CMD="ewarn"
	return 0
}

eerror() {
	elog_base ERROR "$*"
	[[ ${RC_ENDCOL} != "yes" && ${LAST_E_CMD} == "ebegin" ]] && echo
	echo -e " ${BAD}*${NORMAL} ${RC_INDENTATION}$*"
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
		echo -e "${ENDCOL}  ${msg}"
	else
		[[ ${LAST_E_CMD} == ebegin ]] || LAST_E_LEN=0
		printf "%$(( COLS - LAST_E_LEN - 6 ))s%b\n" '' "${msg}"
	fi

	return ${retval}
}

eend() {
	local retval=${1:-0}
	shift

	_eend ${retval} eerror "$*"

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
	COLS="25 80"
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
	COLS=$((${COLS} - 8))	# width of [ ok ] == 7
	# Adjust COLS so that eend works properly on a standard BSD console.
	[ "${TERM}" = "cons25" ] && COLS=$((${COLS} - 1))

	ENDCOL=$'\e[A\e['${COLS}'C'    # Now, ${ENDCOL} will move us to the end of the
	                               # column;  irregardless of character width
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

true
