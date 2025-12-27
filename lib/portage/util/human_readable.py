# Copyright 2025 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["bytes_to_human"]


def bytes_to_human(size: int, decimal_places: int = 2) -> str:
    """
    Converts a size in bytes to a human-readable format (B, KiB, MiB, GiB, TiB, PiB).

    Args:
        size (int): The size in bytes.
        decimal_places (int): The number of decimal places for the output.

    Returns:
        str: Human-readable string.
    """
    for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
        if size < 1024.0 or unit == "PiB":
            break
        size /= 1024.0

    return f"{size:.{decimal_places}f} {unit}"
