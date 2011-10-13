#!@PORTAGE_BASH@
# Copyright 2010-2011 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

PYTHON_VERSIONS="2.6 2.7 3.1 3.2 3.3"

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

exit_status="0"
for version in ${PYTHON_VERSIONS}; do
	if [[ -x @PREFIX_PORTAGE_PYTHON@${version} ]]; then
		echo -e "${GOOD}Testing with Python ${version}...${NORMAL}"
		if ! @PREFIX_PORTAGE_PYTHON@${version} -Wd pym/portage/tests/runTests "$@" ; then
			echo -e "${BAD}Testing with Python ${version} failed${NORMAL}"
			exit_status="1"
		fi
		echo
	fi
done

exit ${exit_status}
