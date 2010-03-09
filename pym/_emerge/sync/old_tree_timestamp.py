# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

import locale
import logging
import time

from portage import os
from portage.exception import PortageException
from portage.localization import _
from portage.util import grabfile, writemsg_level, writemsg_stdout

def have_english_locale():
	lang, enc = locale.getdefaultlocale()
	if lang is not None:
		lang = lang.lower()
		lang = lang.split('_', 1)[0]
	return lang is None or lang in ('c', 'en')

def whenago(seconds):
	sec = int(seconds)
	mins = 0
	days = 0
	hrs = 0
	years = 0
	out = []

	if sec > 60:
		mins = sec / 60
		sec = sec % 60
	if mins > 60:
		hrs = mins / 60
		mins = mins % 60
	if hrs > 24:
		days = hrs / 24
		hrs = hrs % 24
	if days > 365:
		years = days / 365
		days = days % 365

	if years:
		out.append(str(years)+"y ")
	if days:
		out.append(str(days)+"d ")
	if hrs:
		out.append(str(hrs)+"h ")
	if mins:
		out.append(str(mins)+"m ")
	if sec:
		out.append(str(sec)+"s ")

	return "".join(out).strip()

def old_tree_timestamp_warn(portdir, settings):
	unixtime = time.time()
	default_warnsync = 30

	timestamp_file = os.path.join(portdir, "metadata/timestamp.x")
	try:
		lastsync = grabfile(timestamp_file)
	except PortageException:
		return False

	if not lastsync:
		return False

	lastsync = lastsync[0].split()
	if not lastsync:
		return False

	try:
		lastsync = int(lastsync[0])
	except ValueError:
		return False

	var_name = 'PORTAGE_SYNC_STALE'
	try:
		warnsync = float(settings.get(var_name, default_warnsync))
	except ValueError:
		writemsg_level("!!! %s contains non-numeric value: %s\n" % \
			(var_name, settings[var_name]),
			level=logging.ERROR, noiselevel=-1)
		return False

	if warnsync <= 0:
		return False

	if (unixtime - 86400 * warnsync) > lastsync:
		if have_english_locale():
			writemsg_stdout(">>> Last emerge --sync was %s ago\n" % \
				whenago(unixtime - lastsync), noiselevel=-1)
		else:
			writemsg_stdout(">>> %s\n" % \
				_("Last emerge --sync was %s") % \
				time.strftime('%c', time.localtime(lastsync)),
				noiselevel=-1)
		return True
	return False
