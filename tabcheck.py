#!/usr/bin/env python -b

import sys
import tabnanny

for x in sys.argv:
    tabnanny.check(x)
