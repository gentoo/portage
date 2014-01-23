#!/usr/bin/python -bO

import tabnanny,sys

for x in sys.argv:
	tabnanny.check(x)
