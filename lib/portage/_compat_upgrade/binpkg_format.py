# Copyright 2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import re

import portage
from portage import os
from portage.const import GLOBAL_CONFIG_PATH

COMPAT_BINPKG_FORMAT = "xpak"


def main():
    """
    If the current installation is still configured to use the old
    default BINPKG_FORMAT=xpak setting, then patch make.globals
    inside ${ED} to maintain backward compatibility, ensuring that
    binary package consumers are not caught off guard. This is
    intended to be called from the ebuild as follows:

    pkg_preinst() {
            python_setup
            env -u BINPKG_FORMAT
                    PYTHONPATH="${D%/}$(python_get_sitedir)${PYTHONPATH:+:${PYTHONPATH}}" \
                    "${PYTHON}" -m portage._compat_upgrade.binpkg_format || die
    }
    """
    if (
        portage.settings.get("BINPKG_FORMAT", COMPAT_BINPKG_FORMAT)
        == COMPAT_BINPKG_FORMAT
    ):
        config_path = os.path.join(
            os.environ["ED"], GLOBAL_CONFIG_PATH.lstrip(os.sep), "make.globals"
        )
        with open(config_path) as f:
            content = f.read()
            compat_setting = f'BINPKG_FORMAT="{COMPAT_BINPKG_FORMAT}"'
            portage.output.EOutput().einfo(
                "Setting make.globals default {} for backward compatibility".format(
                    compat_setting
                )
            )
            content = re.sub(
                "^BINPKG_FORMAT=.*$", compat_setting, content, flags=re.MULTILINE
            )
        with open(config_path, "w") as f:
            f.write(content)


if __name__ == "__main__":
    main()
