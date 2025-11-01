# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import datetime

__all__ = ["unix_to_iso_time"]


def unix_to_iso_time(unix_ts):
    local_timezone = datetime.datetime.now().astimezone().tzinfo
    dt = datetime.datetime.fromtimestamp(
        int(unix_ts),
        local_timezone,
    )
    return dt.isoformat()
