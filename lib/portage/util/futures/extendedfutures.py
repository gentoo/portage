# Copyright 2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
#
# This module provides an extended subset of the asyncio.futures.Futures
# interface.

__all__ = (
	'CancelledError',
	'ExtendedFuture',
	'InvalidStateError',
)

from portage.util.futures.futures import (Future, InvalidStateError,
	CancelledError)

# Create our one time settable unset constant
UNSET_CONST = Future()
UNSET_CONST.set_result(object())


class ExtendedFuture(Future):
	'''Extended Future class adding convienince get and set operations with
	default result capabilities for unset result().  It also adds pass
	capability for duplicate set_result() calls.
	'''

	def __init__(self, default_result=UNSET_CONST.result()):
		'''Class init

		@param default_result: Optional data type/value to return in the event
		                       of a result() call when result has not yet been
		                       set.
		'''
		self.default_result = default_result
		super(ExtendedFuture, self).__init__()
		self.set = self.set_result

	def set_result(self, data, ignore_InvalidState=False):
		'''Set the Future's result to the data, optionally don't raise
		an error for 'InvalidStateError' errors

		@param ignore_exception: Boolean
		'''
		if ignore_InvalidState:
			try:
				super(ExtendedFuture, self).set_result(data)
			except InvalidStateError:
				pass
		else:
			super(ExtendedFuture, self).set_result(data)

	def get(self, default=UNSET_CONST.result()):
		'''Convienience function to wrap result() but adds an optional
		default value to return rather than raise an InvalidStateError

		@param default: Optional override for the classwide default_result
		@returns: the result data or the default value, raisies an exception
		          if result is unset and no default is defined.
		'''
		if default is not UNSET_CONST.result():
			pass
		elif self.default_result is not UNSET_CONST.result():
			default = self.default_result
		if default is not UNSET_CONST.result():
			try:
				data = super(ExtendedFuture, self).result()
			except InvalidStateError:
				data = default
		else:
			data = super(ExtendedFuture, self).result()
		return data
