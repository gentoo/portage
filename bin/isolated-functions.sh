# Copyright 1999-2004 Gentoo Technologies, Inc.
# Distributed under the terms of the GNU General Public License v2
# $Header$

# Internal logging function, don't use this in ebuilds
elog_base() {
	local messagetype
	[ -z "${1}" -o -z "${T}" -o ! -d "${T}/logging" ] && return 1
	case "${1}" in
		INFO|WARN|ERROR|LOG)
			messagetype="${1}"
			shift
			;;
		*)
			echo -e " ${BAD}*${NORMAL} Invalid use of internal function elog_base(), next message will not be logged"
			return 1
			;;
	esac
	echo ${*} >> ${T}/logging/${EBUILD_PHASE}.${messagetype}
	return 0
}

elog() {
	elog_base LOG ${*}
	echo -e " ${GOOD}*${NORMAL} ${*}"
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
	einfon ${*}
	echo
	return 0
}

einfon() {
	elog_base INFO ${*}
	echo -ne " ${GOOD}*${NORMAL} ${*}"
	return 0
}

ewarn() {
	elog_base WARN ${*}
	echo -e " ${WARN}*${NORMAL} ${*}"
	return 0
}

eerror() {
	elog_base ERROR ${*}
	echo -e " ${BAD}*${NORMAL} ${*}"
	return 0
}

ebegin() {
	if [ -z "${NOCOLOR}" ]; then
		echo -ne " ${GOOD}*${NORMAL} ${*}..."
	else
		echo -e " ${GOOD}*${NORMAL} ${*}..."
	fi
	return 0
}

eend() {
	local retval=
	if [ "$#" -eq 0 ] || [ "${1:-1}" -eq  0 ]; then
		echo -e "${ENDCOL}  ${BRACKET}[ ${GOOD}ok${BRACKET} ]${NORMAL}"
	else
		retval="$1"
		
		if [ "$#" -ge 2 ]
		then
			shift
			eerror "${*}"
		fi
		echo -e "${ENDCOL}  ${BRACKET}[ ${BAD}!!${BRACKET} ]${NORMAL}"
		# extra spacing makes it easier to read
		echo
		return ${retval}
	fi
	return 0
}

KV_major() {
	local KV=
	
	[ -z "$1" ] && return 1

	KV="$(echo "$1" | \
		awk '{ tmp = $0; gsub(/^[0-9\.]*/, "", tmp); sub(tmp, ""); print }')"
	echo "${KV}" | awk -- 'BEGIN { FS = "." } { print $1 }'

	return 0
}

KV_minor() {
	local KV=
	
	[ -z "$1" ] && return 1

	KV="$(echo "$1" | \
		awk '{ tmp = $0; gsub(/^[0-9\.]*/, "", tmp); sub(tmp, ""); print }')"
	echo "${KV}" | awk -- 'BEGIN { FS = "." } { print $2 }'

	return 0
}

KV_micro() {
	local KV=
	
	[ -z "$1" ] && return 1

	KV="$(echo "$1" | \
		awk '{ tmp = $0; gsub(/^[0-9\.]*/, "", tmp); sub(tmp, ""); print }')"
	echo "${KV}" | awk -- 'BEGIN { FS = "." } { print $3 }'

	return 0
}

KV_to_int() {
	local KV_MAJOR=
	local KV_MINOR=
	local KV_MICRO=
	local KV_int=
	
	[ -z "$1" ] && return 1
    
	KV_MAJOR="$(KV_major "$1")"
	KV_MINOR="$(KV_minor "$1")"
	KV_MICRO="$(KV_micro "$1")"
	KV_int="$((KV_MAJOR * 65536 + KV_MINOR * 256 + KV_MICRO))"
    
	# We make version 2.2.0 the minimum version we will handle as
	# a sanity check ... if its less, we fail ...
	if [ "${KV_int}" -ge 131584 ]
	then 
		echo "${KV_int}"

		return 0
	fi

	return 1
}   

get_KV() {
	local KV="$(uname -r)"

	echo "$(KV_to_int "${KV}")"

	return $?
}

getcols() {
	echo "$2"
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
	
	if [ -n "${EBUILD}" ] && [ "${*/depend}" = "$*" ]; then
		stty cols 80 &>/dev/null
		stty rows 25 &>/dev/null
	fi
}

set_colors() {
	COLS="`stty size 2> /dev/null`"
	COLS="`getcols ${COLS}`"
	COLS=$((${COLS} - 7))
	ENDCOL=$'\e[A\e['${COLS}'G'    # Now, ${ENDCOL} will move us to the end of the
	                               # column;  irregardless of character width
	
	GOOD=$'\e[32;01m'
	WARN=$'\e[33;01m'
	BAD=$'\e[31;01m'
	NORMAL=$'\e[0m'
	HILITE=$'\e[36;01m'
	BRACKET=$'\e[34;01m'
}
true
