#!/usr/bin/env -S python -b

import tabnanny,sys

for x in sys.argv:
	tabnanny.check(x)
