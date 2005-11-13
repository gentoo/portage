import os, time
from portage_data import portage_uid, portage_gid

def process(mysettings, cpv, logentries, fulltext):
	cpv_path = cpv.replace("/", ":")

	elogdir = mysettings["PORTAGE_TMPDIR"]+"/elogs"
	if not os.path.exists(elogdir):
		os.makedirs(elogdir)
	os.chown(elogdir, portage_uid, portage_gid)
	os.chmod(elogdir, 0770)

	elogfilename = elogdir+"/"+cpv_path+":"+time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time()))+".log"
	elogfile = open(elogfilename, "w")
	elogfile.write(fulltext)
	elogfile.close()

	return
