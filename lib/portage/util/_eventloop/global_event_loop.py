# Copyright 2012-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ('global_event_loop',)

from portage.util.futures._asyncio import _safe_loop as global_event_loop
