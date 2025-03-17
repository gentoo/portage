#!/usr/bin/env bash
# Copyright 2024-2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# @FUNCTION: __pipestatus
# @USAGE: [-v]
# @RETURN: last non-zero element of PIPESTATUS, or zero if all are zero
# @DESCRIPTION:
# Check the PIPESTATUS array, i.e. the exit status of the command(s)
# in the most recently executed foreground pipeline.  If called with
# option -v, also output the PIPESTATUS array.
__pipestatus() {
	local status=( "${PIPESTATUS[@]}" )
	local s ret=0 verbose=""

	[[ ${1} == -v ]] && { verbose=1; shift; }
	[[ $# -ne 0 ]] && die "usage: ${FUNCNAME} [-v]"

	for s in "${status[@]}"; do
		[[ ${s} -ne 0 ]] && ret=${s}
	done

	[[ ${verbose} ]] && echo "${status[@]}"

	return "${ret}"
}
