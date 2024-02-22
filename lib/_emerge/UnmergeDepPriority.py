# Copyright 1999-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from _emerge.AbstractDepPriority import AbstractDepPriority


class UnmergeDepPriority(AbstractDepPriority):
    __slots__ = (
        "cross",
        "ignored",
        "optional",
        "satisfied",
    )
    """
    Combination of properties           Priority  Category

    installtime                            0       HARD
    runtime_slot_op                       -1       HARD
    runtime                               -2       HARD
    runtime_post                          -3       HARD
    buildtime                             -4       SOFT
    (none of the above)                   -4       SOFT
    """

    MAX = 0
    SOFT = -4
    MIN = -4

    def __init__(self, **kwargs):
        AbstractDepPriority.__init__(self, **kwargs)
        if self.buildtime:
            self.optional = True

    def __int__(self):
        if self.installtime:
            return 0
        if self.runtime_slot_op:
            return -1
        if self.runtime:
            return -2
        if self.runtime_post:
            return -3
        if self.buildtime:
            return -4
        return -4

    def __str__(self):
        if self.ignored:
            return "ignored"
        if self.installtime:
            return "install time"
        if self.runtime_slot_op:
            return "hard slot op"
        myvalue = self.__int__()
        if myvalue > self.SOFT:
            return "hard"
        return "soft"
