# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: /var/cvsroot/gentoo-src/portage/pym/Attic/portage_db_flat.py,v 1.13.2.6 2005/04/19 07:14:17 ferringb Exp $
cvs_id_string="$Id: portage_db_flat.py,v 1.13.2.6 2005/04/19 07:14:17 ferringb Exp $"[5:-2]

import types
import os
import stat

import portage_db_template

class database(portage_db_template.database):
	def module_init(self):
		self.lastkey  = None # Cache
		self.lastval  = None # Cache

		self.fullpath = self.path + "/" + self.category + "/"

		if not os.path.exists(self.fullpath):
			prevmask=os.umask(0)
			os.makedirs(self.fullpath, 02775)
			os.umask(prevmask)
			try:
				os.chown(self.fullpath, self.uid, self.gid)
				os.chmod(self.fullpath, 02775)
			except SystemExit, e:
				raise
			except:
				pass
		
	def has_key(self,key):
		if os.path.exists(self.fullpath+key):
			return 1
		return 0
	
	def keys(self):
		# XXX: NEED TOOLS SEPERATED
		# return portage.listdir(self.fullpath,filesonly=1)
		mykeys = []
		for x in os.listdir(self.fullpath):
			if os.path.isfile(self.fullpath+x) and not x.startswith(".update."):
				mykeys += [x]
		return mykeys

	def get_values(self,key):
		if not key:
			raise KeyError, "key is not set to a valid value"

		try:
			# give buffering a hint of the pretty much maximal cache size we deal with
			myf = open(self.fullpath+key, "r", 8192)
		except OSError, oe:
			# either the file didn't exist, or it was removed under our feet.
			return None 
		

		# nuke the newlines right off the batt.
		data = myf.read().splitlines()
		mdict = {}
		
		# rely on exceptions to note differing line counts.
		try:
			for x in range(0, len(self.dbkeys)):
				mdict[self.dbkeys[x]] = data[x]

			# do this now, rather then earlier- possible that earlier it might have been wasted
			# if key count mismatched
			mdict["_mtime_"] = os.fstat(myf.fileno()).st_mtime

		except IndexError:
			myf.close()
			raise ValueError, "Key count mistmatch"

		myf.close()
		return mdict
	
	def set_values(self,key,val):
		if not key:
			raise KeyError, "No key provided. key:%s val:%s" % (key,val)
		if not val:
			raise ValueError, "No value provided. key:%s val:%s" % (key,val)
			
		# XXX threaded cache updates won't play nice with this.
		# need a synchronization primitive, or locking (of the fileno, not a seperate file)
		# to correctly handle threading.

		update_fp = self.fullpath + ".update." + str(os.getpid()) + "." + key
		myf = open(update_fp,"w")
		myf.writelines( [ val[x] +"\n" for x in self.dbkeys] )
		myf.close()
		
		os.chown(update_fp, self.uid, self.gid)
		os.chmod(update_fp, 0664)
		os.utime(update_fp, (-1,long(val["_mtime_"])))
		os.rename(update_fp, self.fullpath+key)

	def del_key(self,key):
		try:
			os.unlink(self.fullpath+key)
		except OSError, oe:
			# just attempt it without checking, due to the fact that
			# a cache update could be in progress.
			self.lastkey = None
			self.lastval = None
			return 0
		return 1
			
	def sync(self):
		return
	
	def close(self):
		return
	
