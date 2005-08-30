# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/Attic/portage_db_template.py,v 1.11.2.1 2005/01/16 02:35:33 carpaski Exp $


import os.path,string
from portage_util import getconfig, ReadOnlyConfig
from portage_exception import CorruptionError

class database:
	def __init__(self,path,category,dbkeys,uid,gid,config_path="/etc/portage/module_configs/"):
		self.__cacheArray = [None, None, None]
		self.__cacheKeyArray = [None, None, None]
		self.__template_init_called = True
		self.path     = path
		self.category = category
		self.dbkeys   = dbkeys
		self.uid      = uid
		self.gid      = gid

		self.config   = None
		self.__load_config(config_path)

		self.module_init()
	
	def getModuleName(self):
		return self.__module__+"."+self.__class__.__name__[:]

	def __load_config(self,config_path):
		config_file = config_path + "/" + self.getModuleName()
		self.config = ReadOnlyConfig(config_file)

	def __check_init(self):
		try:
			if self.__template_init_called:
				pass
		except SystemExit, e:
			raise
		except:
			raise NotImplementedError("db_template.__init__ was overridden")

	def check_key(self,key):
		if (not key) or not isinstance(key, str):
			raise KeyError, "No key provided. key: %s" % (key)
	
	def clear(self):
		for x in self.keys():
			self.del_key(x)

	def __addCache(self,key,val):
		del self.__cacheArray[2]
		self.__cacheArray.insert(0,val)
		del self.__cacheKeyArray[2]
		self.__cacheKeyArray.insert(0,key)

	def __delCache(self,key):
		i = self.__cacheKeyArray.index(key)
		self.__cacheArray[i] = None
		self.__cacheKeyArray[i] = None

	def flushCache(self):
		self.__cacheArray = [None, None, None]
		self.__cacheKeyArray = [None, None, None]

	def __getitem__(self,key):
		if key in self.__cacheKeyArray:
			i = self.__cacheKeyArray.index(key)
			return self.__cacheArray[i]

		self.check_key(key)
		if self.has_key(key):
			try:
				values = self.get_values(key)
				self.__addCache(key,values)
				return values
			except SystemExit, e:
				raise
			except Exception, e:
				raise CorruptionError("Corruption detected when reading key '%s': %s" % (key,str(e)))
		raise KeyError("Key not in db: '%s'" % (key))
	
	def __setitem__(self,key,values):
		self.check_key(key)
		self.__addCache(key,values)
		return self.set_values(key,values)

	def __delitem__(self,key):
		self.__delCache(key)
		return self.del_key(key)

	def has_key(self,key):
		raise NotImplementedError("Method not defined")
	
	def keys(self):
		raise NotImplementedError("Method not defined")

	def get_values(self,key):
		raise NotImplementedError("Method not defined")
	
	def set_values(self,key,val):
		raise NotImplementedError("Method not defined")

	def del_key(self,key):
		raise NotImplementedError("Method not defined")
			
	def sync(self):
		raise NotImplementedError("Method not defined")
	
	def close(self):
		raise NotImplementedError("Method not defined")


	
def test_database(db_class,path,category,dbkeys,uid,gid):
	if "_mtime_" not in dbkeys:
		dbkeys+=["_mtime_"]
	d = db_class(path,category,dbkeys,uid,gid)

	print "Module: "+str(d.__module__)

	# XXX: Need a way to do this that actually works.
	for x in dir(database):
		if x not in dir(d):
			print "FUNCTION MISSING:",str(x)

	list = d.keys()
	if(len(list) == 0):
		values = {}
		for x in dbkeys:
			values[x] = x[:]
		values["_mtime_"] = "1079903037"
		d.set_values("test-2.2.3-r1", values)
		d.set_values("test-2.2.3-r2", values)
		d.set_values("test-2.2.3-r3", values)
		d.set_values("test-2.2.3-r4", values)

	list = d.keys()
	print "Key count:",len(list)

	values = d.get_values(list[0])
	print "value count:",len(values)
	
	mykey = "foobar-1.2.3-r4"
	
	d.check_key(mykey)
	d.set_values(mykey, values)
	d.sync()
	del d

	d = db_class(path,category,dbkeys,uid,gid)
	new_vals = d.get_values(mykey)

	if dbkeys and new_vals:
		for x in dbkeys:
			if x not in new_vals.keys():
				print "---",x
		for x in new_vals.keys():
			if x not in dbkeys:
				print "+++",x
	else:
		print "Mismatched:",dbkeys,new_vals
	
	d.del_key(mykey)
	
	print "Should be None:",d.get_values(mykey)

	d.clear()

	d.sync
	d.close
	
	del d
	
	print "Done."
