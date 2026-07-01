# Copyright 2016-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = [
    "ConfigParserError",
    "NoOptionError",
    "ParsingError",
    "RawConfigParser",
    "SafeConfigParser",
    "read_configs",
]

# the following scary compatibility thing provides two classes:
# - SafeConfigParser that provides safe interpolation for values,
# - RawConfigParser that provides no interpolation for values.

import io

from configparser import (
    Error as ConfigParserError,
    NoOptionError,
    ParsingError,
    RawConfigParser,
)
from configparser import ConfigParser as SafeConfigParser


def read_configs(parser, paths):
    """
    Read configuration files from given paths into the specified
    ConfigParser, handling path encoding portably.
    @param parser: target *ConfigParser instance
    @type parser: SafeConfigParser or RawConfigParser
    @param paths: list of paths to read
    @type paths: iterable
    """
    for p in paths:
        if isinstance(p, str):
            f = None
            try:
                f = open(
                    p,
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                pass
            else:
                parser.read_file(f, source=p)
            finally:
                if f is not None:
                    f.close()
        elif isinstance(p, io.StringIO):
            parser.read_file(p, source="<io.StringIO>")
        else:
            raise TypeError(
                f"Unsupported type {type(p)!r} of element {p!r} of 'paths' argument"
            )
