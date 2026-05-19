# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import platform
import sys
import time

from portage.output import darkgreen, green


class stdout_spinner:
    scroll_msgs = [
        "Gentoo Rocks (" + platform.system() + ")",
        "Thank you for using Gentoo. :)",
        "Are you actually trying to read this?",
        "How many times have you stared at this?",
        "We are generating the cache right now",
        "You are paying too much attention.",
        "A theory is better than its explanation.",
        "Phasers locked on target, Captain.",
        "Thrashing is just virtual crashing.",
        "To be is to program.",
        "Real Users hate Real Programmers.",
        "When all else fails, read the instructions.",
        "Functionality breeds Contempt.",
        "The future lies ahead.",
        "3.1415926535897932384626433832795028841971694",
        "Sometimes insanity is the only alternative.",
        "Inaccuracy saves a world of explanation.",
    ]

    twirl_sequence = r"/-\|"

    def __init__(self):
        self.update = self.update_twirl
        self.scroll_sequence = self.scroll_msgs[
            int(time.time() * 100) % len(self.scroll_msgs)
        ]
        self.min_display_latency = 0.08
        self.start_time = time.monotonic()
        self.last_frame = -1
        self.scroll_prefix = ""

    def _frame_index(self):
        return int((time.monotonic() - self.start_time) / self.min_display_latency)

    def update_static(self):
        # No animation required. This is used when --nospinner is specified,
        # TERM has a value of "dumb", or sys.stdout.isatty() is false. Kept
        # distinct from update_quiet(), which suppresses the notice altogether.
        return True

    def update_scroll(self):
        frame = self._frame_index()
        if frame == self.last_frame:
            return True
        seq_len = len(self.scroll_sequence)
        cycle_len = 2 * seq_len
        pos = frame % cycle_len
        if pos >= seq_len:
            pos = cycle_len - pos - 1
            char = darkgreen(self.scroll_sequence[pos])
        else:
            char = green(self.scroll_sequence[pos])
        sys.stdout.write(f"\r{self.scroll_prefix}{' ' * pos}{char}\x1b[K")
        self.last_frame = frame
        sys.stdout.flush()
        return True

    def update_twirl(self):
        frame = self._frame_index()
        if frame == self.last_frame:
            return True
        self.last_frame = frame
        sys.stdout.write(
            "\b\b " + self.twirl_sequence[frame % len(self.twirl_sequence)]
        )
        sys.stdout.flush()
        return True

    def update_quiet(self):
        return True
