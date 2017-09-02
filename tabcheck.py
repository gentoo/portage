#!/usr/bin/python -b

import tabnanny,sys

for x in sys.argv:
	tabnanny.check(x)
