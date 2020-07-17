# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from asyncio.transports import Transport as _Transport


class _FlowControlMixin(_Transport):
	"""
	This is identical to the standard library's private
	asyncio.transports._FlowControlMixin class.

	All the logic for (write) flow control in a mix-in base class.

	The subclass must implement get_write_buffer_size().  It must call
	_maybe_pause_protocol() whenever the write buffer size increases,
	and _maybe_resume_protocol() whenever it decreases.  It may also
	override set_write_buffer_limits() (e.g. to specify different
	defaults).

	The subclass constructor must call super().__init__(extra).  This
	will call set_write_buffer_limits().

	The user may call set_write_buffer_limits() and
	get_write_buffer_size(), and their protocol's pause_writing() and
	resume_writing() may be called.
	"""

	def __init__(self, extra=None, loop=None):
		super().__init__(extra)
		assert loop is not None
		self._loop = loop
		self._protocol_paused = False
		self._set_write_buffer_limits()

	def _maybe_pause_protocol(self):
		size = self.get_write_buffer_size()
		if size <= self._high_water:
			return
		if not self._protocol_paused:
			self._protocol_paused = True
			try:
				self._protocol.pause_writing()
			except Exception as exc:
				self._loop.call_exception_handler({
					'message': 'protocol.pause_writing() failed',
					'exception': exc,
					'transport': self,
					'protocol': self._protocol,
				})

	def _maybe_resume_protocol(self):
		if (self._protocol_paused and
			self.get_write_buffer_size() <= self._low_water):
			self._protocol_paused = False
			try:
				self._protocol.resume_writing()
			except Exception as exc:
				self._loop.call_exception_handler({
					'message': 'protocol.resume_writing() failed',
					'exception': exc,
					'transport': self,
					'protocol': self._protocol,
				})

	def get_write_buffer_limits(self):
		return (self._low_water, self._high_water)

	def _set_write_buffer_limits(self, high=None, low=None):
		if high is None:
			if low is None:
				high = 64*1024
			else:
				high = 4*low
		if low is None:
			low = high // 4
		if not high >= low >= 0:
			raise ValueError('high (%r) must be >= low (%r) must be >= 0' %
							 (high, low))
		self._high_water = high
		self._low_water = low

	def set_write_buffer_limits(self, high=None, low=None):
		self._set_write_buffer_limits(high=high, low=low)
		self._maybe_pause_protocol()

	def get_write_buffer_size(self):
		raise NotImplementedError
