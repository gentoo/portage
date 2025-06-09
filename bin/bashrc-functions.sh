#!/usr/bin/env bash
# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

register_die_hook() {
	local hook

	for hook; do
		if [[ ${hook} != +([![:space:]]) ]]; then
			continue
		elif ! contains_word "${hook}" "${EBUILD_DEATH_HOOKS}"; then
			export EBUILD_DEATH_HOOKS+=" ${hook}"
		fi
	done
}

register_success_hook() {
	local hook

	for hook; do
		if [[ ${hook} != +([![:space:]]) ]]; then
			continue
		elif ! contains_word "${hook}" "${EBUILD_SUCCESS_HOOKS}"; then
			export EBUILD_SUCCESS_HOOKS+=" ${hook}"
		fi
	done
}

__strip_duplicate_slashes() {
	local str=$1 reset_extglob

	if [[ ${str} ]]; then
		# The extglob option affects the behaviour of the parser and
		# must thus be treated with caution. Given that extglob is not
		# normally enabled by portage, use eval to conceal the pattern.
		reset_extglob=$(shopt -p extglob)
		eval "shopt -s extglob; str=\${str//+(\/)/\/}; ${reset_extglob}"
		printf '%s\n' "${str}"
	fi
}

KV_major() {
	[[ -z ${1} ]] && return 1

	local KV=$1
	echo "${KV%%.*}"
}

KV_minor() {
	[[ -z ${1} ]] && return 1

	local KV=$1
	KV=${KV#*.}
	echo "${KV%%.*}"
}

KV_micro() {
	[[ -z ${1} ]] && return 1

	local KV=$1
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
