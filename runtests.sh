#!/usr/bin/env bash
# Copyright 2010-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

# These are the versions we care about.  The rest are just "nice to have".
PYTHON_SUPPORTED_VERSIONS="2.6 2.7 3.2 3.3"
PYTHON_VERSIONS="2.6 2.7 2.7-pypy-1.8 2.7-pypy-1.9 2.7-pypy-2.0 3.1 3.2 3.3 3.4"

# has to be run from portage root dir
cd "${0%/*}" || exit 1

case "${NOCOLOR:-false}" in
	yes|true)
		GOOD=
		BAD=
		NORMAL=
		;;
	no|false)
		GOOD=$'\e[1;32m'
		BAD=$'\e[1;31m'
		NORMAL=$'\e[0m'
		;;
esac

interrupted() {
	echo "interrupted." >&2
	exit 1
}

trap interrupted SIGINT

unused_args=()
IGNORE_MISSING_VERSIONS=true

while [ $# -gt 0 ] ; do
	case "$1" in
		--python-versions=*)
			PYTHON_VERSIONS=${1#--python-versions=}
			IGNORE_MISSING_VERSIONS=false
			;;
		--python-versions)
			shift
			PYTHON_VERSIONS=$1
			IGNORE_MISSING_VERSIONS=false
			;;
		*)
			unused_args[${#unused_args[@]}]=$1
			;;
	esac
	shift
done
if [[ ${PYTHON_VERSIONS} == "supported" ]] ; then
	PYTHON_VERSIONS=${PYTHON_SUPPORTED_VERSIONS}
fi

set -- "${unused_args[@]}"

eprefix=${PORTAGE_OVERRIDE_EPREFIX}
exit_status="0"
found_versions=()
status_array=()
for version in ${PYTHON_VERSIONS}; do
	if [[ $version =~ ^([[:digit:]]+\.[[:digit:]]+)-pypy-([[:digit:]]+\.[[:digit:]]+)$ ]] ; then
		executable=${eprefix}/usr/bin/pypy-c${BASH_REMATCH[2]}
	else
		executable=${eprefix}/usr/bin/python${version}
	fi
	if [[ -x "${executable}" ]]; then
		echo -e "${GOOD}Testing with Python ${version}...${NORMAL}"
		"${executable}" -b -Wd pym/portage/tests/runTests "$@"
		status=$?
		status_array[${#status_array[@]}]=${status}
		found_versions[${#found_versions[@]}]=${version}
		if [ ${status} -ne 0 ] ; then
			echo -e "${BAD}Testing with Python ${version} failed${NORMAL}"
			exit_status="1"
		fi
		echo
	elif [[ ${IGNORE_MISSING_VERSIONS} != "true" ]] ; then
		echo -e "${BAD}Could not find requested Python ${version}${NORMAL}"
		exit_status="1"
	fi
done

if [ ${#status_array[@]} -gt 0 ] ; then
	max_len=0
	for version in ${found_versions[@]} ; do
		[ ${#version} -gt ${max_len} ] && max_len=${#version}
	done
	(( columns = max_len + 2 ))
	(( columns >= 7 )) || columns=7
	printf "\nSummary:\n\n"
	printf "| %-${columns}s | %s\n|" "Version" "Status"
	(( total_cols = columns + 11 ))
	eval "printf -- '-%.0s' {1..${total_cols}}"
	printf "\n"
	row=0
	for version in ${found_versions[@]} ; do
		if [ ${status_array[${row}]} -eq 0 ] ; then
			status="success"
		else
			status="fail"
		fi
		printf "| %-${columns}s | %s\n" "${version}" "${status}"
		(( row++ ))
	done
fi

exit ${exit_status}
