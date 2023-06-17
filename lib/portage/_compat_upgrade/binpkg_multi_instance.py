# Copyright 2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage
from portage import os
from portage.const import GLOBAL_CONFIG_PATH

COMPAT_FEATURES = 'FEATURES="${FEATURES} -binpkg-multi-instance"'


def main():
    """
    If the current installation is still has binpkg-multi-instance
    disabled, then patch make.globals inside ${ED} to maintain backward
    compatibility. This is intended to be called from the ebuild as
    follows:

    pkg_preinst() {
            python_setup
            env -u FEATURES -u PORTAGE_REPOSITORIES \
                    PYTHONPATH="${D}$(python_get_sitedir)${PYTHONPATH:+:${PYTHONPATH}}" \
                    "${PYTHON}" -m portage._compat_upgrade.binpkg_multi_instance || die
    }
    """
    if "binpkg-multi-instance" not in portage.settings.features:
        portage.output.EOutput().einfo(
            f"Setting make.globals default {COMPAT_FEATURES} for backward compatibility"
        )
        config_path = os.path.join(
            os.environ["ED"], GLOBAL_CONFIG_PATH.lstrip(os.sep), "make.globals"
        )
        with open(config_path, "a") as f:
            f.write(f"{COMPAT_FEATURES}\n")


if __name__ == "__main__":
    main()
