# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import locale
import logging
import time

from portage import os, _unicode_decode
from portage.exception import PortageException
from portage.localization import _
from portage.output import EOutput
from portage.util import grabfile, writemsg_level

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
		mins = sec // 60
		sec = sec % 60
	if mins > 60:
		hrs = mins // 60
		mins = mins % 60
	if hrs > 24:
		days = hrs // 24
		hrs = hrs % 24
	if days > 365:
		years = days // 365
		days = days % 365

	if years:
		out.append("%dy " % years)
	if days:
		out.append("%dd " % days)
	if hrs:
		out.append("%dh " % hrs)
	if mins:
		out.append("%dm " % mins)
	if sec:
		out.append("%ds " % sec)

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
		out = EOutput()
		if have_english_locale():
			out.ewarn("Last emerge --sync was %s ago." % \
				whenago(unixtime - lastsync))
		else:
			out.ewarn(_("Last emerge --sync was %s.") % \
				_unicode_decode(time.strftime(
				'%c', time.localtime(lastsync))))
		return True
	return False
