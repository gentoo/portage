# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/Attic/portage_db_cpickle.py,v 1.9.2.2 2005/04/23 07:26:04 jstubbs Exp $
cvs_id_string="$Id: portage_db_cpickle.py,v 1.9.2.2 2005/04/23 07:26:04 jstubbs Exp $"[5:-2]

import anydbm,cPickle,types
from os import chown,access,R_OK,unlink
import os

import portage_db_template

class database(portage_db_template.database):
	def module_init(self):
		self.modified = False
		
		prevmask=os.umask(0)
		if not os.path.exists(self.path):
			os.makedirs(self.path, 02775)

		self.filename = self.path + "/" + self.category + ".cpickle"
		
		if access(self.filename, R_OK):
			try:
				mypickle=cPickle.Unpickler(open(self.filename,"r"))
				mypickle.find_global=None
				self.db = mypickle.load()
			except SystemExit, e:
				raise
			except:
				self.db = {}
		else:
			self.db = {}

		os.umask(prevmask)

	def has_key(self,key):
		self.check_key(key)
		if self.db.has_key(key):
			return 1
		return 0
		
	def keys(self):
		return self.db.keys()
	
	def get_values(self,key):
		self.check_key(key)
		if self.db.has_key(key):
			return self.db[key]
		return None
	
	def set_values(self,key,val):
		self.modified = True
		self.check_key(key)
		self.db[key] = val
	
	def del_key(self,key):
		if self.has_key(key):
			del self.db[key]
			self.modified = True
			return True
		return False
			
	def sync(self):
		if self.modified:
			try:
				if os.path.exists(self.filename):
					unlink(self.filename)
				cPickle.dump(self.db, open(self.filename,"w"), -1)
				os.chown(self.filename,self.uid,self.gid)
				os.chmod(self.filename, 0664)
			except SystemExit, e:
				raise
			except:
				pass
	
	def close(self):
		self.sync()
		self.db = None;
	
