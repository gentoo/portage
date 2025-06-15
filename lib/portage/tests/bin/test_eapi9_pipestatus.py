# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import subprocess
import tempfile
import itertools

from portage.const import PORTAGE_BIN_PATH
from portage.tests import TestCase


class TestEAPI9Pipestatus(TestCase):
    test_script_prelude = """\
pipestatus() {
	__pipestatus "$@"
}

tps() {
    local cmd=${1}
    eval "${cmd}; pipestatus"
    echo $?
}

tpsv() {
    local cmd=${1}
    local out ret
    out=$(eval "${cmd}; pipestatus -v")
    ret=$?
    echo $ret $out
}

ret() {
    return ${1}
}

die() {
    if [[ $@ ]]; then
        2>&1 echo "$@"
    fi
    exit 42
}
"""

    def _test_pipestatus(self, test_cases):
        with tempfile.NamedTemporaryFile("w") as test_script:
            test_script.write(f'source "{PORTAGE_BIN_PATH}"/eapi9-pipestatus.sh\n')
            test_script.write(self.test_script_prelude)
            for cmd, _ in test_cases:
                test_script.write(f"{cmd}\n")

            test_script.flush()

            s = subprocess.Popen(
                ["bash", test_script.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            sout, serr = s.communicate()
            self.assertEqual(s.returncode, 0)
            for test_case, result in zip(test_cases, sout.decode().splitlines()):
                cmd, exp = test_case
                self.assertEqual(
                    result, exp, f"{cmd} -> '{result}' but expected: {exp}"
                )

    def test_pipestatus(self):
        test_cases = [
            # (command, expected exit status)
            ("true", 0),
            ("false", 1),
            ("true | true", 0),
            ("false | true", 1),
            ("true | false", 1),
            ("ret 2 | true", 2),
            ("true | false | true", 1),
            ("true |false | ret 5 | true", 5),
        ]
        test_cases = itertools.starmap(lambda a, b: (f"tps {a}", f"{b}"), test_cases)
        self._test_pipestatus(test_cases)

    def test_pipestatus_v(self):
        test_cases = [
            # (command, expected exit status, expected output)
            ("true | true | true", 0, "0 0 O"),
            ("false | true", 1, "1 0"),
            ("ret 3 | ret 2 | true", 2, "3 2 0"),
        ]
        test_cases = itertools.starmap(
            lambda a, b, c: (f"tpsv {a}", f"{b} {c}"), test_cases
        )
        self._test_pipestatus(test_cases)

    def test_pipestatus_xfail(self):
        test_cases = [
            "pipestatus bad_arg",
            "pipestatus -v extra_arg",
        ]
        for cmd in test_cases:
            with tempfile.NamedTemporaryFile("w") as test_script:
                test_script.write(f'source "{PORTAGE_BIN_PATH}"/eapi9-pipestatus.sh\n')
                test_script.write(self.test_script_prelude)
                test_script.write(f"{cmd}\n")

                test_script.flush()
                s = subprocess.Popen(
                    ["bash", test_script.name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                s.wait()
                self.assertEqual(s.returncode, 42)
