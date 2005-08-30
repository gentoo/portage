#!/usr/bin/python -O
# Copyright 2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: /var/cvsroot/gentoo-src/portage/pym/Attic/portage_db_test.py,v 1.3.2.1 2005/01/16 02:35:33 carpaski Exp $


import portage
import portage_db_template
import portage_db_anydbm
import portage_db_flat
import portage_db_cpickle

import os

uid = os.getuid()
gid = os.getgid()

portage_db_template.test_database(portage_db_flat.database,"/var/cache/edb/dep",   "sys-apps",portage.auxdbkeys,uid,gid)
portage_db_template.test_database(portage_db_cpickle.database,"/var/cache/edb/dep","sys-apps",portage.auxdbkeys,uid,gid)
portage_db_template.test_database(portage_db_anydbm.database,"/var/cache/edb/dep", "sys-apps",portage.auxdbkeys,uid,gid)

