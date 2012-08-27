# Copyright 1999-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import errno
import fcntl
import logging
import os
import select
import signal
import time

from portage.util import writemsg_level
from ..SlotObject import SlotObject
from .PollConstants import PollConstants
from .PollSelectAdapter import PollSelectAdapter

class EventLoop(object):

	supports_multiprocessing = True

	# TODO: Find out why SIGCHLD signals aren't delivered during poll
	# calls, forcing us to wakeup in order to receive them.
	_sigchld_interval = 250

	class _child_callback_class(SlotObject):
		__slots__ = ("callback", "data", "pid", "source_id")

	class _idle_callback_class(SlotObject):
		__slots__ = ("args", "callback", "calling", "source_id")

	class _io_handler_class(SlotObject):
		__slots__ = ("args", "callback", "f", "source_id")

	class _timeout_handler_class(SlotObject):
		__slots__ = ("args", "function", "calling", "interval", "source_id",
			"timestamp")

	def __init__(self, main=True):
		"""
		@param main: If True then this is a singleton instance for use
			in the main thread, otherwise it is a local instance which
			can safely be use in a non-main thread (default is True, so
			that global_event_loop does not need constructor arguments)
		@type main: bool
		"""
		self._use_signal = main
		self._poll_event_queue = []
		self._poll_event_handlers = {}
		self._poll_event_handler_ids = {}
		# Increment id for each new handler.
		self._event_handler_id = 0
		self._idle_callbacks = {}
		self._timeout_handlers = {}
		self._timeout_interval = None

		try:
			select.epoll
		except AttributeError:
			self._poll_obj = create_poll_instance()
			self.IO_ERR = PollConstants.POLLERR
			self.IO_HUP = PollConstants.POLLHUP
			self.IO_IN = PollConstants.POLLIN
			self.IO_NVAL = PollConstants.POLLNVAL
			self.IO_OUT = PollConstants.POLLOUT
			self.IO_PRI = PollConstants.POLLPRI
		else:
			self._poll_obj = _epoll_adapter(select.epoll())
			self.IO_ERR = select.EPOLLERR
			self.IO_HUP = select.EPOLLHUP
			self.IO_IN = select.EPOLLIN
			self.IO_NVAL = 0
			self.IO_OUT = select.EPOLLOUT
			self.IO_PRI = select.EPOLLPRI

		self._child_handlers = {}
		self._sigchld_read = None
		self._sigchld_write = None
		self._sigchld_src_id = None
		self._pid = os.getpid()

	def _poll(self, timeout=None):
		"""
		All poll() calls pass through here. The poll events
		are added directly to self._poll_event_queue.
		In order to avoid endless blocking, this raises
		StopIteration if timeout is None and there are
		no file descriptors to poll.
		"""

		if timeout is None and \
			not self._poll_event_handlers:
			raise StopIteration(
				"timeout is None and there are no poll() event handlers")

		while True:
			try:
				self._poll_event_queue.extend(self._poll_obj.poll(timeout))
				break
			except (IOError, select.error) as e:
				# Silently handle EINTR, which is normal when we have
				# received a signal such as SIGINT (epoll objects may
				# raise IOError rather than select.error, at least in
				# Python 3.2).
				if not (e.args and e.args[0] == errno.EINTR):
					writemsg_level("\n!!! select error: %s\n" % (e,),
						level=logging.ERROR, noiselevel=-1)
				del e

				# This typically means that we've received a SIGINT, so
				# raise StopIteration in order to break out of our current
				# iteration and respond appropriately to the signal as soon
				# as possible.
				raise StopIteration("interrupted")

	def iteration(self, *args):
		"""
		Like glib.MainContext.iteration(), runs a single iteration.
		@type may_block: bool
		@param may_block: if True the call may block waiting for an event
			(default is True).
		@rtype: bool
		@return: True if events were dispatched.
		"""

		may_block = True

		if args:
			if len(args) > 1:
				raise TypeError(
					"expected at most 1 argument (%s given)" % len(args))
			may_block = args[0]

		event_queue =  self._poll_event_queue
		event_handlers = self._poll_event_handlers
		events_handled = 0

		if not event_handlers:
			if self._run_timeouts():
				events_handled += 1
			if not event_handlers:
				if not events_handled and may_block and \
					self._timeout_interval is not None:
					# Block so that we don't waste cpu time by looping too
					# quickly. This makes EventLoop useful for code that needs
					# to wait for timeout callbacks regardless of whether or
					# not any IO handlers are currently registered.
					try:
						self._poll(timeout=self._timeout_interval)
					except StopIteration:
						pass
					if self._run_timeouts():
						events_handled += 1

			# If any timeouts have executed, then return immediately,
			# in order to minimize latency in termination of iteration
			# loops that they may control.
			if events_handled or not event_handlers:
				return bool(events_handled)

		if not event_queue:

			if may_block:
				if self._child_handlers:
					if self._timeout_interval is None:
						timeout = self._sigchld_interval
					else:
						timeout = min(self._sigchld_interval,
							self._timeout_interval)
				else:
					timeout = self._timeout_interval
			else:
				timeout = 0

			try:
				self._poll(timeout=timeout)
			except StopIteration:
				# This can be triggered by EINTR which is caused by signals.
				pass

		# NOTE: IO event handlers may be re-entrant, in case something
		# like AbstractPollTask._wait_loop() needs to be called inside
		# a handler for some reason.
		while event_queue:
			events_handled += 1
			f, event = event_queue.pop()
			x = event_handlers[f]
			if not x.callback(f, event, *x.args):
				self.source_remove(x.source_id)

		# Run timeouts last, in order to minimize latency in
		# termination of iteration loops that they may control.
		if self._run_timeouts():
			events_handled += 1

		return bool(events_handled)

	def child_watch_add(self, pid, callback, data=None):
		"""
		Like glib.child_watch_add(), sets callback to be called with the
		user data specified by data when the child indicated by pid exits.
		The signature for the callback is:

			def callback(pid, condition, user_data)

		where pid is is the child process id, condition is the status
		information about the child process and user_data is data.

		@type int
		@param pid: process id of a child process to watch
		@type callback: callable
		@param callback: a function to call
		@type data: object
		@param data: the optional data to pass to function
		@rtype: int
		@return: an integer ID
		"""
		self._event_handler_id += 1
		source_id = self._event_handler_id
		self._child_handlers[source_id] = self._child_callback_class(
			callback=callback, data=data, pid=pid, source_id=source_id)

		if self._use_signal:
			if self._sigchld_read is None:
				self._sigchld_read, self._sigchld_write = os.pipe()
				fcntl.fcntl(self._sigchld_read, fcntl.F_SETFL,
					fcntl.fcntl(self._sigchld_read,
					fcntl.F_GETFL) | os.O_NONBLOCK)

			# The IO watch is dynamically registered and unregistered as
			# needed, since we don't want to consider it as a valid source
			# of events when there are no child listeners. It's important
			# to distinguish when there are no valid sources of IO events,
			# in order to avoid an endless poll call if there's no timeout.
			if self._sigchld_src_id is None:
				self._sigchld_src_id = self.io_add_watch(
					self._sigchld_read, self.IO_IN, self._sigchld_io_cb)
				signal.signal(signal.SIGCHLD, self._sigchld_sig_cb)

		# poll now, in case the SIGCHLD has already arrived
		self._poll_child_processes()
		return source_id

	def _sigchld_sig_cb(self, signum, frame):
		# If this signal handler was not installed by the
		# current process then the signal doesn't belong to
		# this EventLoop instance.
		if os.getpid() == self._pid:
			os.write(self._sigchld_write, b'\0')

	def _sigchld_io_cb(self, fd, events):
		try:
			while True:
				os.read(self._sigchld_read, 4096)
		except OSError:
			# read until EAGAIN
			pass
		self._poll_child_processes()
		return True

	def _poll_child_processes(self):
		if not self._child_handlers:
			return False

		calls = 0

		for x in list(self._child_handlers.values()):
			if x.source_id not in self._child_handlers:
				# it's already been called via re-entrance
				continue
			try:
				wait_retval = os.waitpid(x.pid, os.WNOHANG)
			except OSError as e:
				if e.errno != errno.ECHILD:
					raise
				del e
				self.source_remove(x.source_id)
			else:
				# With waitpid and WNOHANG, only check the
				# first element of the tuple since the second
				# element may vary (bug #337465).
				if wait_retval[0] != 0:
					calls += 1
					self.source_remove(x.source_id)
					x.callback(x.pid, wait_retval[1], x.data)

		return bool(calls)

	def idle_add(self, callback, *args):
		"""
		Like glib.idle_add(), if callback returns False it is
		automatically removed from the list of event sources and will
		not be called again.

		@type callback: callable
		@param callback: a function to call
		@rtype: int
		@return: an integer ID
		"""
		self._event_handler_id += 1
		source_id = self._event_handler_id
		self._idle_callbacks[source_id] = self._idle_callback_class(
			args=args, callback=callback, source_id=source_id)
		return source_id

	def _run_idle_callbacks(self):
		if not self._idle_callbacks:
			return
		# Iterate of our local list, since self._idle_callbacks can be
		# modified during the exection of these callbacks.
		for x in list(self._idle_callbacks.values()):
			if x.source_id not in self._idle_callbacks:
				# it got cancelled while executing another callback
				continue
			if x.calling:
				# don't call it recursively
				continue
			x.calling = True
			try:
				if not x.callback(*x.args):
					self.source_remove(x.source_id)
			finally:
				x.calling = False

	def timeout_add(self, interval, function, *args):
		"""
		Like glib.timeout_add(), interval argument is the number of
		milliseconds between calls to your function, and your function
		should return False to stop being called, or True to continue
		being called. Any additional positional arguments given here
		are passed to your function when it's called.
		"""
		self._event_handler_id += 1
		source_id = self._event_handler_id
		self._timeout_handlers[source_id] = \
			self._timeout_handler_class(
				interval=interval, function=function, args=args,
				source_id=source_id, timestamp=time.time())
		if self._timeout_interval is None or self._timeout_interval > interval:
			self._timeout_interval = interval
		return source_id

	def _run_timeouts(self):

		calls = 0
		if not self._use_signal:
			if self._poll_child_processes():
				calls += 1

		self._run_idle_callbacks()

		if not self._timeout_handlers:
			return bool(calls)

		ready_timeouts = []
		current_time = time.time()
		for x in self._timeout_handlers.values():
			elapsed_seconds = current_time - x.timestamp
			# elapsed_seconds < 0 means the system clock has been adjusted
			if elapsed_seconds < 0 or \
				(x.interval - 1000 * elapsed_seconds) <= 0:
				ready_timeouts.append(x)

		# Iterate of our local list, since self._timeout_handlers can be
		# modified during the exection of these callbacks.
		for x in ready_timeouts:
			if x.source_id not in self._timeout_handlers:
				# it got cancelled while executing another timeout
				continue
			if x.calling:
				# don't call it recursively
				continue
			calls += 1
			x.calling = True
			try:
				x.timestamp = time.time()
				if not x.function(*x.args):
					self.source_remove(x.source_id)
			finally:
				x.calling = False

		return bool(calls)

	def io_add_watch(self, f, condition, callback, *args):
		"""
		Like glib.io_add_watch(), your function should return False to
		stop being called, or True to continue being called. Any
		additional positional arguments given here are passed to your
		function when it's called.

		@type f: int or object with fileno() method
		@param f: a file descriptor to monitor
		@type condition: int
		@param condition: a condition mask
		@type callback: callable
		@param callback: a function to call
		@rtype: int
		@return: an integer ID of the event source
		"""
		if f in self._poll_event_handlers:
			raise AssertionError("fd %d is already registered" % f)
		self._event_handler_id += 1
		source_id = self._event_handler_id
		self._poll_event_handler_ids[source_id] = f
		self._poll_event_handlers[f] = self._io_handler_class(
			args=args, callback=callback, f=f, source_id=source_id)
		self._poll_obj.register(f, condition)
		return source_id

	def source_remove(self, reg_id):
		"""
		Like glib.source_remove(), this returns True if the given reg_id
		is found and removed, and False if the reg_id is invalid or has
		already been removed.
		"""
		x = self._child_handlers.pop(reg_id, None)
		if x is not None:
			if not self._child_handlers and self._use_signal:
				signal.signal(signal.SIGCHLD, signal.SIG_DFL)
				self.source_remove(self._sigchld_src_id)
				self._sigchld_src_id = None
			return True
		idle_callback = self._idle_callbacks.pop(reg_id, None)
		if idle_callback is not None:
			return True
		timeout_handler = self._timeout_handlers.pop(reg_id, None)
		if timeout_handler is not None:
			if timeout_handler.interval == self._timeout_interval:
				if self._timeout_handlers:
					self._timeout_interval = \
						min(x.interval for x in self._timeout_handlers.values())
				else:
					self._timeout_interval = None
			return True
		f = self._poll_event_handler_ids.pop(reg_id, None)
		if f is None:
			return False
		self._poll_obj.unregister(f)
		if self._poll_event_queue:
			# Discard any unhandled events that belong to this file,
			# in order to prevent these events from being erroneously
			# delivered to a future handler that is using a reallocated
			# file descriptor of the same numeric value (causing
			# extremely confusing bugs).
			remaining_events = []
			discarded_events = False
			for event in self._poll_event_queue:
				if event[0] == f:
					discarded_events = True
				else:
					remaining_events.append(event)

			if discarded_events:
				self._poll_event_queue[:] = remaining_events

		del self._poll_event_handlers[f]
		return True

_can_poll_device = None

def can_poll_device():
	"""
	Test if it's possible to use poll() on a device such as a pty. This
	is known to fail on Darwin.
	@rtype: bool
	@return: True if poll() on a device succeeds, False otherwise.
	"""

	global _can_poll_device
	if _can_poll_device is not None:
		return _can_poll_device

	if not hasattr(select, "poll"):
		_can_poll_device = False
		return _can_poll_device

	try:
		dev_null = open('/dev/null', 'rb')
	except IOError:
		_can_poll_device = False
		return _can_poll_device

	p = select.poll()
	p.register(dev_null.fileno(), PollConstants.POLLIN)

	invalid_request = False
	for f, event in p.poll():
		if event & PollConstants.POLLNVAL:
			invalid_request = True
			break
	dev_null.close()

	_can_poll_device = not invalid_request
	return _can_poll_device

def create_poll_instance():
	"""
	Create an instance of select.poll, or an instance of
	PollSelectAdapter there is no poll() implementation or
	it is broken somehow.
	"""
	if can_poll_device():
		return select.poll()
	return PollSelectAdapter()

class _epoll_adapter(object):
	"""
	Wraps a select.epoll instance in order to make it compatible
	with select.poll instances. This is necessary since epoll instances
	interpret timeout arguments differently. Note that the file descriptor
	that is associated with an epoll instance will close automatically when
	it is garbage collected, so it's not necessary to close it explicitly.
	"""
	__slots__ = ('_epoll_obj',)

	def __init__(self, epoll_obj):
		self._epoll_obj = epoll_obj

	def register(self, fd, *args):
		self._epoll_obj.register(fd, *args)

	def unregister(self, fd):
		self._epoll_obj.unregister(fd)

	def poll(self, *args):
		if len(args) > 1:
			raise TypeError(
				"poll expected at most 2 arguments, got " + \
				repr(1 + len(args)))
		timeout = -1
		if args:
			timeout = args[0]
			if timeout is None or timeout < 0:
				timeout = -1
			elif timeout != 0:
				 timeout = timeout / 1000

		return self._epoll_obj.poll(timeout)
