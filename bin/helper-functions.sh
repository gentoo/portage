#!/usr/bin/env bash
# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# For routines we want to use in ebuild-helpers/ but don't want to
# expose to the general ebuild environment.

source "${PORTAGE_BIN_PATH:?}"/isolated-functions.sh || exit

#
# API functions for doing parallel processing
#
__multijob_init() {
	local pipe

	# Setup a pipe for children to write their pids to when they finish.
	# We have to allocate two fd's because POSIX has undefined behavior
	# when using one single fd for both read and write. #487056
	# However, opening an fd for read or write only will block until the
	# opposite end is opened as well. Thus we open the first fd for both
	# read and write to not block ourselve, but use it for reading only.
	# The second fd really is opened for write only, as Cygwin supports
	# just one single read fd per FIFO. #583962
	pipe=$(mktemp -u -- "${TMPDIR:-/tmp}/multijob.XXXXXX") \
	&& mkfifo -m 600 -- "${pipe}" \
	&& exec {mj_read_fd}<>"${pipe}" \
	&& exec {mj_write_fd}>"${pipe}" \
	&& rm -f -- "${pipe}" \
	|| die "__multijob_init: failed to set up the pipes"

	# See how many children we can fork based on the user's settings.
	mj_max_jobs=$(___makeopts_jobs "$@") || die
	mj_num_jobs=0
}

__multijob_child_init() {
	local exit_routine

	# shellcheck disable=SC2016
	printf -v exit_routine 'echo "${BASHPID} $?" >&%q' "${mj_write_fd}"
	# shellcheck disable=SC2064
	trap "${exit_routine}" EXIT
	trap 'exit 1' INT TERM
}

__multijob_finish_one() {
	local ret

	read -r -u "${mj_read_fd}" _ ret
	(( --mj_num_jobs ))
	return "${ret}"
}

__multijob_finish() {
	local ret=0

	while (( mj_num_jobs > 0 )); do
		__multijob_finish_one
		(( ret |= $? ))
	done
	# Let bash clean up its internal child tracking state.
	wait
	return "${ret}"
}

__multijob_post_fork() {
	if (( ++mj_num_jobs >= mj_max_jobs )); then
		__multijob_finish_one
	fi
}
