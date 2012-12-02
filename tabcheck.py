#!/usr/bin/env python

import tabnanny,sys

for x in sys.argv:
	print ("Tabchecking " + x)
	tabnanny.check(x)
