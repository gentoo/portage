# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import platform
import sys
import threading
import time

from portage.output import darkgreen, green
from portage.process import atexit_register


# Drive stdout_spinner animation from a daemon thread at a steady cadence.
class _SpinnerDriver:
    def __init__(self, spinner, interval):
        self._spinner = spinner
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is None:
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        if self._thread is not None:
            self._stop_event.set()
            self._thread.join()
            self._thread = None

    def _run(self):
        next_update = time.monotonic()
        while True:
            next_update += self._interval
            now = time.monotonic()
            while next_update <= now:
                next_update += self._interval
            if self._stop_event.wait(next_update - now):
                break
            self._spinner.update()


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

    # DECTCEM sequences for controlling cursor visibility.
    hide_cursor_sequence = "\x1b[?25l"
    show_cursor_sequence = "\x1b[?25h"

    def __init__(self):
        self.update = self.update_twirl
        self.scroll_sequence = self.scroll_msgs[
            int(time.time() * 100) % len(self.scroll_msgs)
        ]
        self.min_display_latency = 0.08
        self.start_time = time.monotonic()
        self.last_frame = -1
        self.scroll_prefix = ""
        self.driver = _SpinnerDriver(self, self.min_display_latency)

    def start(self):
        if self.update in (self.update_twirl, self.update_scroll):
            self.driver.start()

    def stop(self):
        self.driver.stop()

    def cancel(self):
        # Stop the spinner without printing a completion message.
        self.stop()
        if self.update in (self.update_twirl, self.update_scroll):
            sys.stdout.write("\r\x1b[K")
            sys.stdout.flush()
            self.show_cursor()
        self.update = self.update_quiet

    def _frame_index(self):
        return int((time.monotonic() - self.start_time) / self.min_display_latency)

    def update_static(self):
        # No animation required. This is used when --nospinner is specified,
        # TERM has a value of "dumb", or sys.stdout.isatty() is false. Kept
        # distinct from update_quiet(), which suppresses the notice altogether.
        pass

    def update_scroll(self):
        frame = self._frame_index()
        if frame == self.last_frame:
            return
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

    def update_twirl(self):
        frame = self._frame_index()
        if frame == self.last_frame:
            return
        if self.last_frame >= 0:
            sys.stdout.write("\b")
        self.last_frame = frame
        sys.stdout.write(self.twirl_sequence[frame % len(self.twirl_sequence)])
        sys.stdout.flush()

    def update_quiet(self):
        pass

    def hide_cursor(self):
        if self.update in (self.update_twirl, self.update_scroll):
            atexit_register(self.show_cursor)
            sys.stdout.write(self.hide_cursor_sequence)
            sys.stdout.flush()

    def show_cursor(self):
        sys.stdout.write(self.show_cursor_sequence)
        sys.stdout.flush()
