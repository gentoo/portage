#!/usr/bin/env python

import tabnanny,sys

for x in sys.argv:
	tabnanny.check(x)
