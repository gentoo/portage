#!/bin/bash

PYTHON_VERSIONS="2.6 2.7 3.1 3.2"

exit_status="0"
for version in ${PYTHON_VERSIONS}; do
	if [[ -x /usr/bin/python${version} ]]; then
		echo -e "\e[1;32mTesting with Python ${version}...\e[0m"
		if ! PYTHONPATH="pym${PYTHONPATH:+:}${PYTHONPATH}" /usr/bin/python${version} pym/portage/tests/runTests; then
			echo -e "\e[1;31mTesting with Python ${version} failed\e[0m"
			exit_status="1"
		fi
		echo
	fi
done

exit ${exit_status}
