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
    # The STATIC mode displays the notice without animation, whereas the QUIET
    # mode suppresses the notice outright.
    QUIET = "quiet"
    STATIC = "static"
    TWIRL = "twirl"
    SCROLL = "scroll"

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
        self.mode = self.TWIRL
        self.scroll_sequence = self.scroll_msgs[
            int(time.time() * 100) % len(self.scroll_msgs)
        ]
        self.min_display_latency = 0.08
        self.start_time = time.monotonic()
        self.last_frame = -1
        self.notice = ""
        self.notice_pending = False
        self.driver = _SpinnerDriver(self, self.min_display_latency)

    def displays_notice(self):
        return self.mode != self.QUIET

    def animates(self):
        return self.mode in (self.TWIRL, self.SCROLL)

    def start(self):
        if self.animates():
            self.driver.start()

    def stop(self):
        self.driver.stop()

    def begin_notice(self, notice):
        # Render the given notice according to the current mode, then start the
        # animation if applicable. It is eventually completed by end_notice(),
        # interrupted by interrupt_notice(), or withdrawn by cancel_notice().
        self.notice = notice
        if self.mode == self.STATIC:
            sys.stdout.write(f"{notice} ...")
            sys.stdout.flush()
        elif self.animates():
            sys.stdout.write(f"{notice} ")
            sys.stdout.flush()
            self.hide_cursor()
        self.notice_pending = self.displays_notice()
        self.start_time = time.monotonic()
        self.last_frame = -1
        self.start()

    def resume_notice(self):
        # Render the notice anew, after having been interrupted.
        self.begin_notice(self.notice)

    def end_notice(self):
        # Stop the spinner, then complete the pending notice. The return value
        # indicates whether there was a displayed notice to complete.
        self.stop()
        if not self.notice_pending:
            return False
        self.notice_pending = False
        if self.mode == self.STATIC:
            sys.stdout.write(" done!\n")
        else:
            sys.stdout.write(f"\r{self.notice} ... done!\x1b[K\n")
            self.show_cursor()
        sys.stdout.flush()
        return True

    def interrupt_notice(self):
        # Stop the spinner, then erase or terminate the pending notice so that
        # further output may cleanly follow. Resumption remains possible, upon
        # which the notice may be rendered anew.
        self.stop()
        if not self.notice_pending:
            return
        self.notice_pending = False
        if self.mode == self.STATIC:
            sys.stdout.write("\n")
        else:
            sys.stdout.write("\r\x1b[K")
            self.show_cursor()
        sys.stdout.flush()

    def cancel_notice(self):
        # Withdraw the pending notice and render nothing further.
        self.interrupt_notice()
        self.mode = self.QUIET

    def _frame_index(self):
        return int((time.monotonic() - self.start_time) / self.min_display_latency)

    def update(self):
        # Render an animation frame on behalf of the driver thread.
        if self.mode == self.TWIRL:
            self._render_twirl()
        elif self.mode == self.SCROLL:
            self._render_scroll()

    def _render_scroll(self):
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
        sys.stdout.write(f"\r{self.notice} {' ' * pos}{char}\x1b[K")
        self.last_frame = frame
        sys.stdout.flush()

    def _render_twirl(self):
        frame = self._frame_index()
        if frame == self.last_frame:
            return
        if self.last_frame >= 0:
            sys.stdout.write("\b")
        self.last_frame = frame
        sys.stdout.write(self.twirl_sequence[frame % len(self.twirl_sequence)])
        sys.stdout.flush()

    def hide_cursor(self):
        if self.animates():
            atexit_register(self.show_cursor)
            sys.stdout.write(self.hide_cursor_sequence)
            sys.stdout.flush()

    def show_cursor(self):
        sys.stdout.write(self.show_cursor_sequence)
        sys.stdout.flush()
