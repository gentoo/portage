#!/usr/bin/python -O

import tabnanny,sys

for x in sys.argv:
	tabnanny.check(x)
