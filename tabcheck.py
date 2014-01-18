#!/usr/bin/python -bbO

import tabnanny,sys

for x in sys.argv:
	tabnanny.check(x)
