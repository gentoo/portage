# Copyright 2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["bin_entry_point"]

import re
import sys

from portage import os_unicode_fs
from portage.const import PORTAGE_BIN_PATH


def bin_entry_point():
    """
    Adjust sys.argv[0] to point to a script in PORTAGE_BIN_PATH, and
    then execute the script, in order to implement entry_points when
    portage has been installed by pip.
    """
    script_path = os_unicode_fs.path.join(
        PORTAGE_BIN_PATH, os_unicode_fs.path.basename(sys.argv[0])
    )
    if os_unicode_fs.access(script_path, os_unicode_fs.X_OK):
        with open(script_path, "rt") as f:
            shebang = f.readline()
        python_match = re.search(r"/python[\d\.]*\s+([^/]*)\s+$", shebang)
        if python_match:
            sys.argv = [
                os_unicode_fs.path.join(
                    os_unicode_fs.path.dirname(sys.argv[0]), "python"
                ),
                python_match.group(1),
                script_path,
            ] + sys.argv[1:]
            os_unicode_fs.execvp(sys.argv[0], sys.argv)
        sys.argv[0] = script_path
        os_unicode_fs.execvp(sys.argv[0], sys.argv)
    else:
        print("File not found:", script_path, file=sys.stderr)
        return 127
