# Copyright 2020-2021 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import logging
import pickle
import shelve


def open_shelve(db_file, flag="r"):
	"""
	The optional flag parameter has the same interpretation as the flag
	parameter of dbm.open()
	"""
	try:
		db = shelve.open(db_file, flag=flag)
	except ImportError as e:
		# ImportError has different attributes for python2 vs. python3
		if getattr(e, "name", None) == "bsddb" or getattr(e, "message", None) in (
			"No module named bsddb",
			"No module named _bsddb",
		):
			from bsddb3 import dbshelve

			db = dbshelve.open(db_file)
		else:
			raise

	return db


def dump(args):
	src = open_shelve(args.src, flag="r")
	try:
		with open(args.dest, "wb") as dest:
			for key in src:
				try:
					value = src[key]
				except KeyError:
					logging.exception(key)
					continue
				pickle.dump((key, value), dest)
	finally:
		src.close()


def restore(args):
	dest = open_shelve(args.dest, flag="c")
	try:
		with open(args.src, "rb") as src:
			while True:
				try:
					k, v = pickle.load(src)
				except EOFError:
					break
				else:
					dest[k] = v
	finally:
		dest.close()
