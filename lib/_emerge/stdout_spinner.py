# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import platform
import sys
import time

from portage.output import darkgreen, green

class stdout_spinner:
	scroll_msgs = [
		"Gentoo Rocks ("+platform.system()+")",
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

	twirl_sequence = "/-\\|/-\\|/-\\|/-\\|\\-/|\\-/|\\-/|\\-/|"

	def __init__(self):
		self.spinpos = 0
		self.update = self.update_twirl
		self.scroll_sequence = self.scroll_msgs[
			int(time.time() * 100) % len(self.scroll_msgs)]
		self.last_update = 0
		self.min_display_latency = 0.05

	def _return_early(self):
		"""
		Flushing ouput to the tty too frequently wastes cpu time. Therefore,
		each update* method should return without doing any output when this
		method returns True.
		"""
		cur_time = time.time()
		if cur_time - self.last_update < self.min_display_latency:
			return True
		self.last_update = cur_time
		return False

	def update_basic(self):
		self.spinpos = (self.spinpos + 1) % 500
		if self._return_early():
			return True
		if (self.spinpos % 100) == 0:
			if self.spinpos == 0:
				sys.stdout.write(". ")
			else:
				sys.stdout.write(".")
		sys.stdout.flush()
		return True

	def update_scroll(self):
		if self._return_early():
			return True
		if self.spinpos >= len(self.scroll_sequence):
			sys.stdout.write(darkgreen(" \b\b\b" + self.scroll_sequence[
				len(self.scroll_sequence) - 1 - (self.spinpos % len(self.scroll_sequence))]))
		else:
			sys.stdout.write(green("\b " + self.scroll_sequence[self.spinpos]))
		sys.stdout.flush()
		self.spinpos = (self.spinpos + 1) % (2 * len(self.scroll_sequence))
		return True

	def update_twirl(self):
		self.spinpos = (self.spinpos + 1) % len(self.twirl_sequence)
		if self._return_early():
			return True
		sys.stdout.write("\b\b " + self.twirl_sequence[self.spinpos])
		sys.stdout.flush()
		return True

	def update_quiet(self):
		return True
