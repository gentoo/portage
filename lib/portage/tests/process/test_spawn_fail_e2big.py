# Copyright 2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import platform
import resource

import pytest

import portage.process
from portage.const import BASH_BINARY


@pytest.mark.skipif(platform.system() != "Linux", reason="not Linux")
def test_spawnE2big(capsys, tmp_path):
    env = dict()
    # Kernel MAX_ARG_STRLEN is defined as 32 * PAGE_SIZE
    max_arg_strlen_bytes = 32 * resource.getpagesize()
    env["VERY_LARGE_ENV_VAR"] = "X" * max_arg_strlen_bytes

    logfile = tmp_path / "logfile"
    echo_output = "Should never appear"
    with capsys.disabled():
        retval = portage.process.spawn(
            [BASH_BINARY, "-c", "echo", echo_output], env=env, logfile=logfile
        )

    with open(logfile) as f:
        logfile_content = f.read()
        assert (
            f"Largest environment variable: VERY_LARGE_ENV_VAR ({max_arg_strlen_bytes + 20} bytes)"
            in logfile_content
        )
    assert retval == 1
