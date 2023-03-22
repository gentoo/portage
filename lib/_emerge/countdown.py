# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import sys
import time

from portage.output import colorize


def countdown(secs=5, doing="Starting"):
    if secs:
        print(
            f">>> Waiting {secs} seconds before starting...\n"
            ">>> (Control-C to abort)...\n"
            f"{doing} in:",
            end="",
        )
        for sec in range(secs, 0, -1):
            sys.stdout.write(colorize("UNMERGE_WARN", f" {sec}"))
            sys.stdout.flush()
            time.sleep(1)
        print()
