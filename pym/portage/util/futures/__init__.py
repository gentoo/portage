# Copyright 2018 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

__all__ = (
	'asyncio',
)

try:
	import asyncio
except ImportError:
	from portage.util.futures import _asyncio as asyncio
