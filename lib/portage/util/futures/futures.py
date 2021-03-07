# Copyright 2016-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2
#
# For compatibility with python versions which do not have the
# asyncio module (Python 3.3 and earlier), this module provides a
# subset of the asyncio.futures.Futures interface.

__all__ = (
	'CancelledError',
	'Future',
	'InvalidStateError',
	'TimeoutError',
)

# pylint: disable=redefined-builtin
from asyncio import (
	CancelledError,
	Future,
	InvalidStateError,
	TimeoutError,
)
