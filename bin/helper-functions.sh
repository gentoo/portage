#!/bin/bash
# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# For routines we want to use in ebuild-helpers/ but don't want to
# expose to the general ebuild environment.

source "${PORTAGE_BIN_PATH:-/usr/lib/portage/bin}"/isolated-functions.sh

#
# API functions for doing parallel processing
#
__numjobs() {
	# Copied from eutils.eclass:makeopts_jobs()
	local jobs=$(echo " ${MAKEOPTS} " | \
		sed -r -n 's:.*[[:space:]](-j|--jobs[=[:space:]])[[:space:]]*([0-9]+).*:\2:p')
	echo ${jobs:-1}
}

__multijob_init() {
	# Setup a pipe for children to write their pids to when they finish.
	mj_control_pipe=$(mktemp -t multijob.XXXXXX)
	rm "${mj_control_pipe}"
	mkfifo "${mj_control_pipe}"
	__redirect_alloc_fd mj_control_fd "${mj_control_pipe}"
	rm -f "${mj_control_pipe}"

	# See how many children we can fork based on the user's settings.
	mj_max_jobs=$(__numjobs)
	mj_num_jobs=0
}

__multijob_child_init() {
	trap 'echo ${BASHPID} $? >&'${mj_control_fd} EXIT
	trap 'exit 1' INT TERM
}

__multijob_finish_one() {
	local pid ret
	read -r -u ${mj_control_fd} pid ret
	: $(( --mj_num_jobs ))
	return ${ret}
}

__multijob_finish() {
	local ret=0
	while [[ ${mj_num_jobs} -gt 0 ]] ; do
		__multijob_finish_one
		: $(( ret |= $? ))
	done
	# Let bash clean up its internal child tracking state.
	wait
	return ${ret}
}

__multijob_post_fork() {
	: $(( ++mj_num_jobs ))
	if [[ ${mj_num_jobs} -ge ${mj_max_jobs} ]] ; then
		__multijob_finish_one
	fi
	return $?
}

# @FUNCTION: __redirect_alloc_fd
# @USAGE: <var> <file> [redirection]
# @DESCRIPTION:
# Find a free fd and redirect the specified file via it.  Store the new
# fd in the specified variable.  Useful for the cases where we don't care
# about the exact fd #.
__redirect_alloc_fd() {
	local var=$1 file=$2 redir=${3:-"<>"}

	if [[ $(( (BASH_VERSINFO[0] << 8) + BASH_VERSINFO[1] )) -ge $(( (4 << 8) + 1 )) ]] ; then
			# Newer bash provides this functionality.
			eval "exec {${var}}${redir}'${file}'"
	else
			# Need to provide the functionality ourselves.
			local fd=10
			while :; do
					# Make sure the fd isn't open.  It could be a char device,
					# or a symlink (possibly broken) to something else.
					if [[ ! -e /dev/fd/${fd} ]] && [[ ! -L /dev/fd/${fd} ]] ; then
							eval "exec ${fd}${redir}'${file}'" && break
					fi
					[[ ${fd} -gt 1024 ]] && die "__redirect_alloc_fd failed"
					: $(( ++fd ))
			done
			: $(( ${var} = fd ))
	fi
}
