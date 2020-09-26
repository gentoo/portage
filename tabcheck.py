#!/usr/bin/env python

import sys
import tabnanny

for x in sys.argv:
	print ("Tabchecking " + x)
	tabnanny.check(x)
