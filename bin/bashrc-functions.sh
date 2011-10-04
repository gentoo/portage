#!/bin/bash
# Copyright 1999-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

portageq() {
	PYTHONPATH=${PORTAGE_PYM_PATH}${PYTHONPATH:+:}${PYTHONPATH} \
	"${PORTAGE_PYTHON:-/usr/bin/python}" "${PORTAGE_BIN_PATH}/portageq" "$@"
}

register_die_hook() {
	local x
	for x in $* ; do
		has $x $EBUILD_DEATH_HOOKS || \
			export EBUILD_DEATH_HOOKS="$EBUILD_DEATH_HOOKS $x"
	done
}

register_success_hook() {
	local x
	for x in $* ; do
		has $x $EBUILD_SUCCESS_HOOKS || \
			export EBUILD_SUCCESS_HOOKS="$EBUILD_SUCCESS_HOOKS $x"
	done
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

# Set given variables unless these variable have been already set (e.g. during emerge
# invocation) to values different than values set in make.conf.
set_unless_changed() {
	if [[ $# -lt 1 ]]; then
		die "${FUNCNAME}() requires at least 1 argument: VARIABLE=VALUE"
	fi

	local argument value variable
	for argument in "$@"; do
		if [[ ${argument} != *=* ]]; then
			die "${FUNCNAME}(): Argument '${argument}' has incorrect syntax"
		fi
		variable="${argument%%=*}"
		value="${argument#*=}"
		if eval "[[ \${${variable}} == \$(env -u ${variable} portageq envvar ${variable}) ]]"; then
			eval "${variable}=\"\${value}\""
		fi
	done
}

# Unset given variables unless these variable have been set (e.g. during emerge
# invocation) to values different than values set in make.conf.
unset_unless_changed() {
	if [[ $# -lt 1 ]]; then
		die "${FUNCNAME}() requires at least 1 argument: VARIABLE"
	fi

	local variable
	for variable in "$@"; do
		if eval "[[ \${${variable}} == \$(env -u ${variable} portageq envvar ${variable}) ]]"; then
			unset ${variable}
		fi
	done
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
