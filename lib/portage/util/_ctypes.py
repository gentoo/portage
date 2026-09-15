# Copyright 2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

try:
    import ctypes
except ImportError:
    ctypes = None


_library_handles = {}


def LoadLibrary(name):
    """
    Calls ctypes.CDLL(name) if the ctypes module is available,
    and otherwise returns None. Results are cached for future invocations.
    """
    handle = _library_handles.get(name)

    if handle is None and ctypes is not None:
        handle = ctypes.CDLL(name, use_errno=True)
        _library_handles[name] = handle

    return handle


def load_libc():
    """
    Loads the C standard library, returns a tuple with the CDLL handle and
    the filename. Returns (None, None) if unavailable.
    """
    # Passing NULL to dlopen() gives access to all global symbols.
    # This includes shared libs loaded at startup (including libc).
    filename = None
    try:
        return (LoadLibrary(filename), filename)
    except OSError:
        return (None, None)
