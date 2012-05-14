#!/bin/bash
# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# For routines we want to use in ebuild-helpers/ but don't want to
# expose to the general ebuild environment.

source "${PORTAGE_BIN_PATH:-/usr/lib/portage/bin}"/isolated-functions.sh

#
# API functions for doing parallel processing
#
numjobs() {
	# Copied from eutils.eclass:makeopts_jobs()
	local jobs=$(echo " ${MAKEOPTS} " | \
		sed -r -n 's:.*[[:space:]](-j|--jobs[=[:space:]])[[:space:]]*([0-9]+).*:\2:p')
	echo ${jobs:-1}
}

multijob_init() {
	# Setup a pipe for children to write their pids to when they finish.
	mj_control_pipe=$(mktemp -t multijob.XXXXXX)
	rm "${mj_control_pipe}"
	mkfifo "${mj_control_pipe}"
	exec {mj_control_fd}<>${mj_control_pipe}
	rm -f "${mj_control_pipe}"

	# See how many children we can fork based on the user's settings.
	mj_max_jobs=$(numjobs)
	mj_num_jobs=0
}

multijob_child_init() {
	trap 'echo ${BASHPID} $? >&'${mj_control_fd} EXIT
	trap 'exit 1' INT TERM
}

multijob_finish_one() {
	local pid ret
	read -r -u ${mj_control_fd} pid ret
	: $(( --mj_num_jobs ))
	return ${ret}
}

multijob_finish() {
	local ret=0
	while [[ ${mj_num_jobs} -gt 0 ]] ; do
		multijob_finish_one
		: $(( ret |= $? ))
	done
	# Let bash clean up its internal child tracking state.
	wait
	return ${ret}
}

multijob_post_fork() {
	: $(( ++mj_num_jobs ))
	if [[ ${mj_num_jobs} -ge ${mj_max_jobs} ]] ; then
		multijob_finish_one
	fi
	return $?
}
