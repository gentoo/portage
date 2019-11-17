#!/bin/bash
# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# For routines we want to use in ebuild-helpers/ but don't want to
# expose to the general ebuild environment.

source "${PORTAGE_BIN_PATH}"/isolated-functions.sh || exit 1

#
# API functions for doing parallel processing
#
__multijob_init() {
	# Setup a pipe for children to write their pids to when they finish.
	# We have to allocate two fd's because POSIX has undefined behavior
	# when using one single fd for both read and write. #487056
	# However, opening an fd for read or write only will block until the
	# opposite end is opened as well. Thus we open the first fd for both
	# read and write to not block ourselve, but use it for reading only.
	# The second fd really is opened for write only, as Cygwin supports
	# just one single read fd per FIFO. #583962
	local pipe
	pipe=$(mktemp -t multijob.XXXXXX) || die
	rm -f "${pipe}"
	mkfifo -m 600 "${pipe}" || die
	__redirect_alloc_fd mj_read_fd "${pipe}"
	__redirect_alloc_fd mj_write_fd "${pipe}" '>'
	rm -f "${pipe}"

	# See how many children we can fork based on the user's settings.
	mj_max_jobs=$(___makeopts_jobs "$@") || die
	mj_num_jobs=0
}

__multijob_child_init() {
	trap 'echo ${BASHPID:-$(__bashpid)} $? >&'${mj_write_fd} EXIT
	trap 'exit 1' INT TERM
}

__multijob_finish_one() {
	local pid ret
	read -r -u ${mj_read_fd} pid ret
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
		local fddir=/dev/fd
		# Prefer /proc/self/fd if available (/dev/fd
		# doesn't work on solaris, see bug #474536).
		[[ -d /proc/self/fd ]] && fddir=/proc/self/fd
		while :; do
			# Make sure the fd isn't open.  It could be a char device,
			# or a symlink (possibly broken) to something else.
			if [[ ! -e ${fddir}/${fd} ]] && [[ ! -L ${fddir}/${fd} ]] ; then
				eval "exec ${fd}${redir}'${file}'" && break
			fi
			[[ ${fd} -gt 1024 ]] && die 'could not locate a free temp fd !?'
			: $(( ++fd ))
		done
		: $(( ${var} = fd ))
	fi
}
