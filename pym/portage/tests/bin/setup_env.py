# setup_env.py -- Make sure bin subdir has sane env for testing
# Copyright 2007 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: test_dep_getcpv.py 6182 2007-03-06 07:35:22Z antarus $

import os, shutil, sys
from os.path import dirname, abspath, join
from portage.tests import TestCase
from portage.process import spawn

bindir = join(dirname(dirname(abspath(__file__))), "..", "..", "..", "bin")
basedir = join(dirname(dirname(abspath(__file__))), "bin", "root")
os.environ["D"] = os.path.join(basedir, "image")
os.environ["T"] = os.path.join(basedir, "temp")
os.environ["S"] = os.path.join(basedir, "workdir")
os.environ["PF"] = "portage-tests-0.09-r1"
os.environ["PATH"] = bindir + ":" + os.environ["PATH"]

def binTestsCleanup():
	if os.access(basedir, os.W_OK):
		shutil.rmtree(basedir)
def binTestsInit():
	binTestsCleanup()
	os.mkdir(basedir)
	os.mkdir(os.environ["D"])
	os.mkdir(os.environ["T"])
	os.mkdir(os.environ["S"])
	os.chdir(os.environ["S"])

class BinTestCase(TestCase):
	def __init__(self, methodName):
		TestCase.__init__(self, methodName)
		binTestsInit()
	def __del__(self):
		binTestsCleanup()
		if hasattr(TestCase, "__del__"):
			TestCase.__del__(self)

def _exists_in_D(path):
	# Note: do not use os.path.join() here, we assume D to end in /
	return os.access(os.environ["D"] + path, os.W_OK)
def exists_in_D(path):
	if not _exists_in_D(path):
		raise TestCase.failureException
def xexists_in_D(path):
	if _exists_in_D(path):
		raise TestCase.failureException

def portage_func(func, args, exit_status=0):
	# we don't care about the output of the programs,
	# just their exit value and the state of $D
	f = open('/dev/null', 'w')
	fd_pipes = {0:0,1:f.fileno(),2:f.fileno()}
	spawn(func+" "+args, env=os.environ, fd_pipes=fd_pipes)
	f.close()

def create_portage_wrapper(bin):
	def derived_func(*args):
		newargs = list(args)
		newargs.insert(0, bin)
		return portage_func(*newargs)
	return derived_func

for bin in os.listdir(bindir):
	if bin.startswith("do") or \
	   bin.startswith("new") or \
	   bin.startswith("prep") or \
	   bin in ["ecompress","ecompressdir","fowners","fperms"]:
		globals()[bin] = create_portage_wrapper(bin)
