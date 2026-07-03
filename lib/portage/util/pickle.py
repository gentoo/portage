# Copyright 2026 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

__all__ = ["NoGlobalsUnpickler"]

import pickle


class NoGlobalsUnpickler(pickle.Unpickler):
    """
    An Unpickler subclass that rejects pickle global references.

    Overrides the find_class() method so that pickle cannot import modules or
    resolve objects by name while loading a stream.

    https://docs.python.org/3/library/pickle.html#restricting-globals
    """

    def find_class(self, module, name):
        raise pickle.UnpicklingError(
            f"pickle global reference '{module}.{name}' is forbidden"
        )
