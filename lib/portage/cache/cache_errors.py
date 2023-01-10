# Copyright: 2005 Gentoo Foundation
# Author(s): Brian Harring (ferringb@gentoo.org)
# License: GPL2


class CacheError(Exception):
    pass


class InitializationError(CacheError):
    def __init__(self, class_name, error):
        self.error, self.class_name = error, class_name

    def __str__(self):
        return f"Creation of instance {self.class_name} failed due to {str(self.error)}"


class CacheCorruption(CacheError):
    def __init__(self, key, ex):
        self.key, self.ex = key, ex

    def __str__(self):
        return f"{self.key} is corrupt: {str(self.ex)}"


class GeneralCacheCorruption(CacheError):
    def __init__(self, ex):
        self.ex = ex

    def __str__(self):
        return f"corruption detected: {str(self.ex)}"


class InvalidRestriction(CacheError):
    def __init__(self, key, restriction, exception=None):
        if exception is None:
            exception = ""
        self.key, self.restriction, self.ex = key, restriction, ex

    def __str__(self):
        return f"{self.key}:{self.restriction} is not valid: {str(self.ex)}"


class ReadOnlyRestriction(CacheError):
    def __init__(self, info=""):
        self.info = info

    def __str__(self):
        return "cache is non-modifiable" + str(self.info)


class StatCollision(CacheError):
    """
    If the content of a cache entry changes and neither the file mtime nor
    size changes, it will prevent rsync from detecting changes. Cache backends
    may raise this exception from _setitem() if they detect this type of stat
    collision. See bug #139134.
    """

    def __init__(self, key, filename, mtime, size):
        self.key = key
        self.filename = filename
        self.mtime = mtime
        self.size = size

    def __str__(self):
        return "{} has stat collision with size {} and mtime {}".format(
            self.key,
            self.size,
            self.mtime,
        )

    def __repr__(self):
        return "portage.cache.cache_errors.StatCollision({})".format(
            ", ".join(
                (repr(self.key), repr(self.filename), repr(self.mtime), repr(self.size))
            ),
        )
