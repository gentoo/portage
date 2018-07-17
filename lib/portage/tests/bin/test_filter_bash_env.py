# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import difflib
import os
import subprocess

import portage
from portage.const import PORTAGE_BIN_PATH
from portage.tests import TestCase


class TestFilterBashEnv(TestCase):
	def testTestFilterBashEnv(self):

		test_cases = (
			(
				'RDEPEND BASH.* _EPATCH_ECLASS',
				br'''declare -ir BASHPID="28997"
declare -rx A="portage-2.3.24.tar.bz2"
declare -- DESKTOP_DATABASE_DIR="/usr/share/applications"
declare PDEPEND="
        !build? (
                >=net-misc/rsync-2.6.4
                userland_GNU? ( >=sys-apps/coreutils-6.4 )
        ) "
declare RDEPEND="
        >=app-arch/tar-1.27
        dev-lang/python-exec:2"
declare -x PF="portage-2.3.24"
declare -a PYTHON_COMPAT=([0]="pypy" [1]="python3_4" [2]="python3_5" [3]="python3_6" [4]="python2_7")
declare -- _EPATCH_ECLASS="1"
declare -- _EUTILS_ECLASS="1"
declare -- f
get_libdir ()
{
    local CONF_LIBDIR;
    if [ -n "${CONF_LIBDIR_OVERRIDE}" ]; then
        echo ${CONF_LIBDIR_OVERRIDE};
    else
        get_abi_LIBDIR;
    fi
}
make_wrapper ()
{
    cat  <<-EOF
export ${var}="\${${var}}:${EPREFIX}${libdir}"
EOF
}
use_if_iuse ()
{
    in_iuse $1 || return 1;
    use $1
}
''',
				br'''declare -x A="portage-2.3.24.tar.bz2"
declare -- DESKTOP_DATABASE_DIR="/usr/share/applications"
declare PDEPEND="
        !build? (
                >=net-misc/rsync-2.6.4
                userland_GNU? ( >=sys-apps/coreutils-6.4 )
        ) "
declare -x PF="portage-2.3.24"
declare -a PYTHON_COMPAT=([0]="pypy" [1]="python3_4" [2]="python3_5" [3]="python3_6" [4]="python2_7")
declare -- _EUTILS_ECLASS="1"
declare -- f
get_libdir ()
{
    local CONF_LIBDIR;
    if [ -n "${CONF_LIBDIR_OVERRIDE}" ]; then
        echo ${CONF_LIBDIR_OVERRIDE};
    else
        get_abi_LIBDIR;
    fi
}
make_wrapper ()
{
    cat  <<-EOF
export ${var}="\${${var}}:${EPREFIX}${libdir}"
EOF
}
use_if_iuse ()
{
    in_iuse $1 || return 1;
    use $1
}
'''),
		)

		for filter_vars, env_in, env_out in test_cases:
			proc = None
			try:
				proc = subprocess.Popen(
					[
						portage._python_interpreter,
						os.path.join(PORTAGE_BIN_PATH, 'filter-bash-environment.py'),
						filter_vars,
					],
					stdin=subprocess.PIPE,
					stdout=subprocess.PIPE,
				)
				proc.stdin.write(env_in)
				proc.stdin.close()
				result = proc.stdout.read()
			finally:
				if proc is not None:
					proc.stdin.close()
					proc.wait()
					proc.stdout.close()

			diff = list(difflib.unified_diff(
				env_out.decode('utf_8').splitlines(),
				result.decode('utf_8').splitlines()))

			self.assertEqual(diff, [])
