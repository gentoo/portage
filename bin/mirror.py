#!/usr/bin/python -O
# Copyright 1999-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/bin/mirror.py,v 1.3 2004/10/10 10:07:20 carpaski Exp $

# Defines the number of threads carrying out the downloading.
maxsems=5

import os,sys,string
os.environ["PORTAGE_CALLER"]="mirror"
os.environ["FEATURES"]="mirror cvs"
sys.path = ["/usr/lib/portage/pym"]+sys.path

import portage
from threading import *
from output import red,green,blue,bold
from random import shuffle
from time import sleep


def cstrip(mystr,mychars):
	newstr = ""
	for x in mystr:
		if x not in mychars:
			newstr += x
	return newstr

class fetcher(Thread):
	def __init__(self, filename, urilist, dest, md5sum):
		self.filename = filename
		self.myurilist = urilist
		self.myuri = None
		self.mydest = dest
		self.destpath = self.mydest+"/"+self.filename
		self.md5sum = md5sum
		self.result = None
		Thread.__init__(self)
	
	def fetch(self):
		#print "Started",self.filename
		sys.stderr.write(".")
		sys.stderr.flush()
		portage.spawn("wget -q -P "+str(self.mydest)+" "+self.myuri, free=1)

	def finished(self):
		if os.path.exists(self.destpath) and self.md5sum:
			ok,reason = portage_checksum.verify_all(self.destpath, md5sum)
			if not ok:
				portage_util.writemsg("Failed verification:"+reason[0]+" (got "+reason[1]+", expected "+reason[2]+"\n")
				return 1
		return 0
	
	def delete(self):
		if os.path.exists(self.destpath):
			#print "Unlink:",self.destpath
			os.unlink(self.destpath)

	def run(self):
		if not self.finished():
			self.delete()

		while not self.finished():
			if self.myurilist:
				self.myuri = self.myurilist.pop(0)+"/"+self.filename
				self.fetch()
			else:
				self.delete()
				self.result = 0
				#print "Failed:",self.filename
				return 1

		#print "Finished:",self.filename
		self.result = 1
		return 0
	
	
uri_list = {}
fetchers = []
fetcher_sem = BoundedSemaphore(value=maxsems)
failures  = 0
successes = 0

def clean_fetchers():
	global fetcher_sem,fetchers,uri_list,failures,successes,maxsems
	while len(fetchers) == maxsems:
		for x in fetchers:
			if not x.isAlive():
				failures  += (x.result == 0)
				successes += (x.result == 1)
				if x.filename in uri_list.keys():
					del uri_list[x.filename]
				del fetchers[fetchers.index(x)]
				fetcher_sem.release()
		if len(fetchers) == maxsems:
			sleep(1)
		

def start_fetcher(fname, urilist, dest, md5sum):
	global fetcher_sem,fetchers,uri_list,failures,successes
	fetcher_sem.acquire()
	fetchers.append(fetcher(fname, urilist, dest, md5sum))
	fetchers[-1].start()


tpm     = portage.thirdpartymirrors
destdir = portage.settings["DISTDIR"][:]

hugelist = []
for mycp in portage.db["/"]["porttree"].dbapi.cp_all():
	hugelist += portage.db["/"]["porttree"].dbapi.cp_list(mycp)
shuffle(hugelist)

mycount = -1
for mycpv in hugelist:
	pv = string.split(mycpv, "/")[-1]

	clean_fetchers()

	mycount += 1
	if ((mycount % 20) == 0):
		sys.stdout.write("\nCompleted: %s\n" % mycount)
		sys.stdout.flush()
	newuri = portage.db["/"]["porttree"].dbapi.aux_get(mycpv,["SRC_URI"])[0]
	newuri = string.split(newuri)

	digestpath = portage.db["/"]["porttree"].dbapi.findname(mycpv)
	digestpath = os.path.dirname(digestpath)+"/files/digest-"+pv
	md5sums    = portage.digestParseFile(digestpath)
	
	for x in newuri:
		clean_fetchers()
		if not x:
			continue
		if (x in [")","(",":","||"]) or (x[-1] == "?"):
			# ignore it. :)
			continue
		x = cstrip(x,"()|?")
		if not x:
			continue
		mybn = os.path.basename(x)
		mydn = os.path.dirname(x)
		if mybn not in uri_list.keys():
			if (len(mybn) > len("mirror://")) and (mybn[:len("mirror://")] == "mirror://"):
				mysite = string.split(x[len("mirror://"):], "/")[0]
				shuffle(tpm[mysite])
				uri_list[mybn] = tpm[mysite][:]
			else:
				uri_list[mybn] = [os.path.dirname(x)]
			clean_fetchers()
			if (not md5sums) or (mybn not in md5sums.keys()):
				start_fetcher(mybn, uri_list[mybn], destdir, None)
			else:
				start_fetcher(mybn, uri_list[mybn], destdir, md5sums[mybn])
		else:
			break

sys.stderr.write("\n\nWaiting last set\n")
sys.stderr.flush()
while fetchers:
	if fetchers[0].isAlive():
		fetchers[0].join()
	clean_fetchers()

print
print
print "Successes:",successes
print "Failures: ",failures
