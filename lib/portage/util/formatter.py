# Copyright 2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#
# This is a minimalistic derivation of Python's deprecated formatter module,
# supporting only the methods related to style, literal data, and line breaks.

import sys


class AbstractFormatter:
	"""The standard formatter."""

	def __init__(self, writer):
		self.writer = writer            # Output device
		self.style_stack = []           # Other state, e.g. color
		self.hard_break = True          # Have a hard break

	def add_line_break(self):
		if not self.hard_break:
			self.writer.send_line_break()
		self.hard_break = True

	def add_literal_data(self, data):
		if not data: return
		self.hard_break = data[-1:] == '\n'
		self.writer.send_literal_data(data)

	def push_style(self, *styles):
		for style in styles:
			self.style_stack.append(style)
		self.writer.new_styles(tuple(self.style_stack))

	def pop_style(self, n=1):
		del self.style_stack[-n:]
		self.writer.new_styles(tuple(self.style_stack))


class NullWriter:
	"""Minimal writer interface to use in testing & inheritance.

	A writer which only provides the interface definition; no actions are
	taken on any methods.  This should be the base class for all writers
	which do not need to inherit any implementation methods.
	"""
	def __init__(self): pass
	def flush(self): pass
	def new_styles(self, styles): pass
	def send_line_break(self): pass
	def send_literal_data(self, data): pass


class DumbWriter(NullWriter):
	"""Simple writer class which writes output on the file object passed in
	as the file parameter or, if file is omitted, on standard output.
	"""

	def __init__(self, file=None, maxcol=None):
		NullWriter.__init__(self)
		self.file = file or sys.stdout

	def flush(self):
		self.file.flush()

	def send_line_break(self):
		self.file.write('\n')

	def send_literal_data(self, data):
		self.file.write(data)
