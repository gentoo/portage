# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import io
import sys
import time

import portage
import portage.util.formatter as formatter
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage.output import xtermTitle

from _emerge.getloadavg import getloadavg

class JobStatusDisplay:

	_bound_properties = ("curval", "failed", "running")

	# Don't update the display unless at least this much
	# time has passed, in units of seconds.
	_min_display_latency = 2

	_default_term_codes = {
		'cr'  : '\r',
		'el'  : '\x1b[K',
		'nel' : '\n',
	}

	_termcap_name_map = {
		'carriage_return' : 'cr',
		'clr_eol'         : 'el',
		'newline'         : 'nel',
	}

	def __init__(self, quiet=False, xterm_titles=True):
		object.__setattr__(self, "quiet", quiet)
		object.__setattr__(self, "xterm_titles", xterm_titles)
		object.__setattr__(self, "maxval", 0)
		object.__setattr__(self, "merges", 0)
		object.__setattr__(self, "_changed", False)
		object.__setattr__(self, "_displayed", False)
		object.__setattr__(self, "_last_display_time", 0)

		self.reset()

		isatty = os.environ.get('TERM') != 'dumb' and \
			hasattr(self.out, 'isatty') and \
			self.out.isatty()
		object.__setattr__(self, "_isatty", isatty)
		if not isatty or not self._init_term():
			term_codes = {}
			for k, capname in self._termcap_name_map.items():
				term_codes[k] = self._default_term_codes[capname]
			object.__setattr__(self, "_term_codes", term_codes)
		encoding = sys.getdefaultencoding()
		for k, v in self._term_codes.items():
			if not isinstance(v, str):
				self._term_codes[k] = v.decode(encoding, 'replace')

		if self._isatty:
			width = portage.output.get_term_size()[1]
		else:
			width = 80
		self._set_width(width)

	def _set_width(self, width):
		if width == getattr(self, 'width', None):
			return
		if width <= 0 or width > 80:
			width = 80
		object.__setattr__(self, "width", width)
		object.__setattr__(self, "_jobs_column_width", width - 32)

	@property
	def out(self):
		"""Use a lazy reference to sys.stdout, in case the API consumer has
		temporarily overridden stdout."""
		return sys.stdout

	def _write(self, s):
		# avoid potential UnicodeEncodeError
		s = _unicode_encode(s,
			encoding=_encodings['stdio'], errors='backslashreplace')
		out = self.out.buffer
		out.write(s)
		out.flush()

	def _init_term(self):
		"""
		Initialize term control codes.
		@rtype: bool
		@return: True if term codes were successfully initialized,
			False otherwise.
		"""

		term_type = os.environ.get("TERM", "").strip()
		if not term_type:
			return False
		tigetstr = None

		try:
			import curses
			try:
				curses.setupterm(term_type, self.out.fileno())
				tigetstr = curses.tigetstr
			except curses.error:
				pass
		except ImportError:
			pass

		if tigetstr is None:
			return False

		term_codes = {}
		for k, capname in self._termcap_name_map.items():
			# Use _native_string for PyPy compat (bug #470258).
			code = tigetstr(portage._native_string(capname))
			if code is None:
				code = self._default_term_codes[capname]
			term_codes[k] = code
		object.__setattr__(self, "_term_codes", term_codes)
		return True

	def _format_msg(self, msg):
		return ">>> %s" % msg

	def _erase(self):
		self._write(
			self._term_codes['carriage_return'] + \
			self._term_codes['clr_eol'])
		self._displayed = False

	def _display(self, line):
		self._write(line)
		self._displayed = True

	def _update(self, msg):

		if not self._isatty:
			self._write(self._format_msg(msg) + self._term_codes['newline'])
			self._displayed = True
			return

		if self._displayed:
			self._erase()

		self._display(self._format_msg(msg))

	def displayMessage(self, msg):

		was_displayed = self._displayed

		if self._isatty and self._displayed:
			self._erase()

		self._write(self._format_msg(msg) + self._term_codes['newline'])
		self._displayed = False

		if was_displayed:
			self._changed = True
			self.display()

	def reset(self):
		self.maxval = 0
		self.merges = 0
		for name in self._bound_properties:
			object.__setattr__(self, name, 0)

		if self._displayed:
			self._write(self._term_codes['newline'])
			self._displayed = False

	def __setattr__(self, name, value):
		old_value = getattr(self, name)
		if value == old_value:
			return
		object.__setattr__(self, name, value)
		if name in self._bound_properties:
			self._property_change(name, old_value, value)

	def _property_change(self, name, old_value, new_value):
		self._changed = True
		self.display()

	def _load_avg_str(self):
		try:
			avg = getloadavg()
		except OSError:
			return 'unknown'

		max_avg = max(avg)

		if max_avg < 10:
			digits = 2
		elif max_avg < 100:
			digits = 1
		else:
			digits = 0

		return ", ".join(("%%.%df" % digits ) % x for x in avg)

	def display(self):
		"""
		Display status on stdout, but only if something has
		changed since the last call. This always returns True,
		for continuous scheduling via timeout_add.
		"""

		if self.quiet:
			return True

		current_time = time.time()
		time_delta = current_time - self._last_display_time
		if self._displayed and \
			not self._changed:
			if not self._isatty:
				return True
			if time_delta < self._min_display_latency:
				return True

		self._last_display_time = current_time
		self._changed = False
		self._display_status()
		return True

	def _display_status(self):
		# Don't use len(self._completed_tasks) here since that also
		# can include uninstall tasks.
		curval_str = "%s" % (self.curval,)
		maxval_str = "%s" % (self.maxval,)
		running_str = "%s" % (self.running,)
		failed_str = "%s" % (self.failed,)
		load_avg_str = self._load_avg_str()

		color_output = io.StringIO()
		plain_output = io.StringIO()
		style_file = portage.output.ConsoleStyleFile(color_output)
		style_file.write_listener = plain_output
		style_writer = portage.output.StyleWriter(file=style_file, maxcol=9999)
		style_writer.style_listener = style_file.new_styles
		f = formatter.AbstractFormatter(style_writer)

		number_style = "INFORM"
		f.add_literal_data("Jobs: ")
		f.push_style(number_style)
		f.add_literal_data(curval_str)
		f.pop_style()
		f.add_literal_data(" of ")
		f.push_style(number_style)
		f.add_literal_data(maxval_str)
		f.pop_style()
		f.add_literal_data(" complete")

		if self.running:
			f.add_literal_data(", ")
			f.push_style(number_style)
			f.add_literal_data(running_str)
			f.pop_style()
			f.add_literal_data(" running")

		if self.failed:
			f.add_literal_data(", ")
			f.push_style(number_style)
			f.add_literal_data(failed_str)
			f.pop_style()
			f.add_literal_data(" failed")

		padding = self._jobs_column_width - len(plain_output.getvalue())
		if padding > 0:
			f.add_literal_data(padding * " ")

		f.add_literal_data("Load avg: ")
		f.add_literal_data(load_avg_str)

		# Truncate to fit width, to avoid making the terminal scroll if the
		# line overflows (happens when the load average is large).
		plain_output = plain_output.getvalue()
		if self._isatty and len(plain_output) > self.width:
			# Use plain_output here since it's easier to truncate
			# properly than the color output which contains console
			# color codes.
			self._update(plain_output[:self.width])
		else:
			self._update(color_output.getvalue())

		if self.xterm_titles:
			# If the HOSTNAME variable is exported, include it
			# in the xterm title, just like emergelog() does.
			# See bug #390699.
			title_str = " ".join(plain_output.split())
			hostname = os.environ.get("HOSTNAME")
			if hostname is not None:
				title_str = "%s: %s" % (hostname, title_str)
			xtermTitle(title_str)
