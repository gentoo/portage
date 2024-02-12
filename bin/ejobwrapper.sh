#!/usr/bin/env bash
# Copyright (c) 2022 Gentoo Authors

_PORTAGE_JOBSERVER_SCRIPT="$(realpath -s ${BASH_SOURCE:-$0})"
_PORTAGE_JOBSERVER_SCRIPT_BASENAME="$(basename "${_PORTAGE_JOBSERVER_SCRIPT}")"

# Skip ebuild setup phase.
if [[ "${EBUILD_PHASE}" == "setup" ]]; then
    :
# Do not pass wrapper to child processes to avoid deadlock. e.g.: rustc call clang.
elif [[ -z "${PORTAGE_JOBSERVER_WRAPPED}" ]]; then

    _PORTAGE_JOBSERVER_ADDRESS="${PORTAGE_JOBSERVER_ADDRESS:=127.0.0.1}"
    _PORTAGE_JOBSERVER_PORT="${PORTAGE_JOBSERVER_PORT:=25721}"
    unset PORTAGE_JOBSERVER_ADDRESS
    unset PORTAGE_JOBSERVER_PORT

    if [[ ${_PORTAGE_JOBSERVER_SCRIPT_BASENAME} == "jobwrapper.sh" ]]; then
        echo "ERROR: do not call jobwrapper.sh directly" >&2
        exit 1
    fi

    if ! exec {JOBSERVER}<>"/dev/tcp/${_PORTAGE_JOBSERVER_ADDRESS}/${_PORTAGE_JOBSERVER_PORT}"; then
	    echo "Failed to contact portage job server, ignoring job control (was bash built with net support?)" >&2
    elif ! read -u ${JOBSERVER} -N 2 _PORTAGE_JOBSERVER_TOKEN; then
	    echo "Failed to acquire portage job server token, ignoring job control." >&2
    else
        if [[ "${_PORTAGE_JOBSERVER_TOKEN}" != "OK" ]]; then
            echo "Job server not allowed new job, stopping..." >&2
            exit 1
        fi
    fi

    PATH="${PATH//'/usr/lib/portage/jobserver:'/}"
    PATH="${PATH//'/usr/local/lib/portage/jobserver:'/}"

    export PATH
    export PORTAGE_JOBSERVER_WRAPPED=1
fi


for cmd in $(type -ap ${_PORTAGE_JOBSERVER_SCRIPT_BASENAME}); do
    if [[ ${_PORTAGE_JOBSERVER_SCRIPT} != "${cmd}" ]]; then
        break
    fi
done

"${cmd}" "${@}"
