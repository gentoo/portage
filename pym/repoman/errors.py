
import sys


def warn(txt):
	print("repoman: " + txt)


def err(txt):
	warn(txt)
	sys.exit(1)


