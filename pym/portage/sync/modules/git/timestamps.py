# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import stat
import subprocess


import portage
from portage import os
from portage import _unicode_decode
from portage.util import writemsg_level
from portage.cache.cache_errors import CacheError


def git_sync_timestamps(portdb, portdir):
	"""
	Since git doesn't preserve timestamps, synchronize timestamps between
	entries and ebuilds/eclasses. Assume the cache has the correct timestamp
	for a given file as long as the file in the working tree is not modified
	(relative to HEAD).
	"""

	cache_db = portdb._pregen_auxdb.get(portdir)

	try:
		if cache_db is None:
			# portdbapi does not populate _pregen_auxdb
			# when FEATURES=metadata-transfer is enabled
			cache_db = portdb._create_pregen_cache(portdir)
	except CacheError as e:
		writemsg_level("!!! Unable to instantiate cache: %s\n" % (e,),
			level=logging.ERROR, noiselevel=-1)
		return 1

	if cache_db is None:
		return os.EX_OK

	if cache_db.validation_chf != 'mtime':
		# newer formats like md5-dict do not require mtime sync
		return os.EX_OK

	writemsg_level(">>> Synchronizing timestamps...\n")

	ec_dir = os.path.join(portdir, "eclass")
	try:
		ec_names = set(f[:-7] for f in os.listdir(ec_dir) \
			if f.endswith(".eclass"))
	except OSError as e:
		writemsg_level("!!! Unable to list eclasses: %s\n" % (e,),
			level=logging.ERROR, noiselevel=-1)
		return 1

	args = [portage.const.BASH_BINARY, "-c",
		"cd %s && git diff-index --name-only --diff-filter=M HEAD" % \
		portage._shell_quote(portdir)]
	proc = subprocess.Popen(args, stdout=subprocess.PIPE)
	modified_files = set(_unicode_decode(l).rstrip("\n") for l in proc.stdout)
	rval = proc.wait()
	proc.stdout.close()
	if rval != os.EX_OK:
		return rval

	modified_eclasses = set(ec for ec in ec_names \
		if os.path.join("eclass", ec + ".eclass") in modified_files)

	updated_ec_mtimes = {}

	for cpv in cache_db:
		cpv_split = portage.catpkgsplit(cpv)
		if cpv_split is None:
			writemsg_level("!!! Invalid cache entry: %s\n" % (cpv,),
				level=logging.ERROR, noiselevel=-1)
			continue

		cat, pn, ver, rev = cpv_split
		cat, pf = portage.catsplit(cpv)
		relative_eb_path = os.path.join(cat, pn, pf + ".ebuild")
		if relative_eb_path in modified_files:
			continue

		try:
			cache_entry = cache_db[cpv]
			eb_mtime = cache_entry.get("_mtime_")
			ec_mtimes = cache_entry.get("_eclasses_")
		except KeyError:
			writemsg_level("!!! Missing cache entry: %s\n" % (cpv,),
				level=logging.ERROR, noiselevel=-1)
			continue
		except CacheError as e:
			writemsg_level("!!! Unable to access cache entry: %s %s\n" % \
				(cpv, e), level=logging.ERROR, noiselevel=-1)
			continue

		if eb_mtime is None:
			writemsg_level("!!! Missing ebuild mtime: %s\n" % (cpv,),
				level=logging.ERROR, noiselevel=-1)
			continue

		try:
			eb_mtime = long(eb_mtime)
		except ValueError:
			writemsg_level("!!! Invalid ebuild mtime: %s %s\n" % \
				(cpv, eb_mtime), level=logging.ERROR, noiselevel=-1)
			continue

		if ec_mtimes is None:
			writemsg_level("!!! Missing eclass mtimes: %s\n" % (cpv,),
				level=logging.ERROR, noiselevel=-1)
			continue

		if modified_eclasses.intersection(ec_mtimes):
			continue

		missing_eclasses = set(ec_mtimes).difference(ec_names)
		if missing_eclasses:
			writemsg_level("!!! Non-existent eclass(es): %s %s\n" % \
				(cpv, sorted(missing_eclasses)), level=logging.ERROR,
				noiselevel=-1)
			continue

		eb_path = os.path.join(portdir, relative_eb_path)
		try:
			current_eb_mtime = os.stat(eb_path)
		except OSError:
			writemsg_level("!!! Missing ebuild: %s\n" % \
				(cpv,), level=logging.ERROR, noiselevel=-1)
			continue

		inconsistent = False
		for ec, (ec_path, ec_mtime) in ec_mtimes.items():
			updated_mtime = updated_ec_mtimes.get(ec)
			if updated_mtime is not None and updated_mtime != ec_mtime:
				writemsg_level("!!! Inconsistent eclass mtime: %s %s\n" % \
					(cpv, ec), level=logging.ERROR, noiselevel=-1)
				inconsistent = True
				break

		if inconsistent:
			continue

		if current_eb_mtime != eb_mtime:
			os.utime(eb_path, (eb_mtime, eb_mtime))

		for ec, (ec_path, ec_mtime) in ec_mtimes.items():
			if ec in updated_ec_mtimes:
				continue
			ec_path = os.path.join(ec_dir, ec + ".eclass")
			current_mtime = os.stat(ec_path)[stat.ST_MTIME]
			if current_mtime != ec_mtime:
				os.utime(ec_path, (ec_mtime, ec_mtime))
			updated_ec_mtimes[ec] = ec_mtime

	return os.EX_OK
