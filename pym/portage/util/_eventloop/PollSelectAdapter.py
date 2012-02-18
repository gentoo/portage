# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from .PollConstants import PollConstants
import select

class PollSelectAdapter(object):

	"""
	Use select to emulate a poll object, for
	systems that don't support poll().
	"""

	def __init__(self):
		self._registered = {}
		self._select_args = [[], [], []]

	def register(self, fd, *args):
		"""
		Only POLLIN is currently supported!
		"""
		if len(args) > 1:
			raise TypeError(
				"register expected at most 2 arguments, got " + \
				repr(1 + len(args)))

		eventmask = PollConstants.POLLIN | \
			PollConstants.POLLPRI | PollConstants.POLLOUT
		if args:
			eventmask = args[0]

		self._registered[fd] = eventmask
		self._select_args = None

	def unregister(self, fd):
		self._select_args = None
		del self._registered[fd]

	def poll(self, *args):
		if len(args) > 1:
			raise TypeError(
				"poll expected at most 2 arguments, got " + \
				repr(1 + len(args)))

		timeout = None
		if args:
			timeout = args[0]

		select_args = self._select_args
		if select_args is None:
			select_args = [list(self._registered), [], []]

		if timeout is not None:
			select_args = select_args[:]
			# Translate poll() timeout args to select() timeout args:
			#
			#          | units        | value(s) for indefinite block
			# ---------|--------------|------------------------------
			#   poll   | milliseconds | omitted, negative, or None
			# ---------|--------------|------------------------------
			#   select | seconds      | omitted
			# ---------|--------------|------------------------------

			if timeout is not None and timeout < 0:
				timeout = None
			if timeout is not None:
				select_args.append(timeout / 1000)

		select_events = select.select(*select_args)
		poll_events = []
		for fd in select_events[0]:
			poll_events.append((fd, PollConstants.POLLIN))
		return poll_events

