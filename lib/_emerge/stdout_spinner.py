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
        cycle_len = 2 * len(self.scroll_sequence)
        start = min(frame, max(self.last_frame + 1, frame - cycle_len + 1))
        for f in range(start, frame + 1):
            pos = f % cycle_len
            if pos >= len(self.scroll_sequence):
                sys.stdout.write(
                    darkgreen(
                        " \b\b\b"
                        + self.scroll_sequence[
                            len(self.scroll_sequence)
                            - 1
                            - (pos % len(self.scroll_sequence))
                        ]
                    )
                )
            else:
                sys.stdout.write(green("\b " + self.scroll_sequence[pos]))
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
