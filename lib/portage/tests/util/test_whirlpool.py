# Copyright 2011-2023 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import pytest

from portage.tests import TestCase
from portage.util.whirlpool import CWhirlpool, PyWhirlpool


CWHIRLPOOL_AVAILABLE = CWhirlpool.is_available
CWHIRLPOOL_NOT_AVAILABLE_MSG = "C Whirlpool extension is not importable"


class WhirlpoolTestCase(TestCase):
    def testBundledWhirlpool(self, cls=PyWhirlpool):
        self.assertEqual(
            cls(b"The quick brown fox jumps over the lazy dog").hexdigest(),
            "b97de512e91e3828b40d2b0fdce9ceb3c4a71f9bea8d88e75c4fa854df36725fd2b52eb6544edcacd6f8beddfea403cb55ae31f03ad62a5ef54e42ee82c3fb35",
        )
        self.assertEqual(
            cls(b"The quick brown fox jumps over the lazy eog").hexdigest(),
            "c27ba124205f72e6847f3e19834f925cc666d0974167af915bb462420ed40cc50900d85a1f923219d832357750492d5c143011a76988344c2635e69d06f2d38c",
        )
        self.assertEqual(
            cls(b"").hexdigest(),
            "19fa61d75522a4669b44e39c1d2e1726c530232130d407f89afee0964997f7a73e83be698b288febcf88e3e03c4f0757ea8964e59b63d93708b138cc42a66eb3",
        )
        w = cls()
        w.update(b"")
        self.assertEqual(
            w.hexdigest(),
            "19fa61d75522a4669b44e39c1d2e1726c530232130d407f89afee0964997f7a73e83be698b288febcf88e3e03c4f0757ea8964e59b63d93708b138cc42a66eb3",
        )

    @pytest.mark.skipif(
        not CWHIRLPOOL_AVAILABLE,
        reason=CWHIRLPOOL_NOT_AVAILABLE_MSG,
    )
    def testCWhirlpool(self):
        if not CWHIRLPOOL_AVAILABLE:
            self.skipTest(CWHIRLPOOL_NOT_AVAILABLE_MSG)
        self.testBundledWhirlpool(CWhirlpool)
