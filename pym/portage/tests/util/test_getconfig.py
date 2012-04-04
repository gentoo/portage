# Copyright 2010-2012 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import tempfile

from portage import os
from portage import _unicode_encode
from portage.const import PORTAGE_BASE_PATH
from portage.tests import TestCase
from portage.util import getconfig

class GetConfigTestCase(TestCase):
	"""
	Test that getconfig() produces that same result as bash would when
	sourcing the same input.
	"""

	_cases = {
		'FETCHCOMMAND'             : 'wget -t 3 -T 60 --passive-ftp -O "${DISTDIR}/${FILE}" "${URI}"',
		'FETCHCOMMAND_RSYNC'       : 'rsync -avP "${URI}" "${DISTDIR}/${FILE}"',
		'FETCHCOMMAND_SFTP'        : 'bash -c "x=\\${2#sftp://} ; host=\\${x%%/*} ; port=\\${host##*:} ; host=\\${host%:*} ; [[ \\${host} = \\${port} ]] && port=22 ; exec sftp -P \\${port} \\"\\${host}:/\\${x#*/}\\" \\"\\$1\\"" sftp "${DISTDIR}/${FILE}" "${URI}"',
		'FETCHCOMMAND_SSH'         : 'bash -c "x=\\${2#ssh://} ; host=\\${x%%/*} ; port=\\${host##*:} ; host=\\${host%:*} ; [[ \\${host} = \\${port} ]] && port=22 ; exec rsync --rsh=\\"ssh -p\\${port}\\" -avP \\"\\${host}:/\\${x#*/}\\" \\"\\$1\\"" rsync "${DISTDIR}/${FILE}" "${URI}"',
		'PORTAGE_ELOG_MAILSUBJECT' : '[portage] ebuild log for ${PACKAGE} on ${HOST}'
	}

	def testGetConfig(self):

		make_globals_file = os.path.join(PORTAGE_BASE_PATH,
			'cnf', 'make.globals')
		d = getconfig(make_globals_file)
		for k, v in self._cases.items():
			self.assertEqual(d[k], v)

	def testGetConfigProfileEnv(self):
		# Test the mode which is used to parse /etc/env.d and /etc/profile.env.

		cases = {
			'LESS_TERMCAP_mb': "$\E[01;31m", # bug #410625
		}

		with tempfile.NamedTemporaryFile(mode='wb') as f:
			# Format like env_update formats /etc/profile.env.
			for k, v in cases.items():
				if v.startswith('$') and not v.startswith('${'):
					line = "export %s=$'%s'\n" % (k, v[1:])
				else:
					line = "export %s='%s'\n" % (k, v)
				f.write(_unicode_encode(line))
			f.flush()

			d = getconfig(f.name, expand=False)
			for k, v in cases.items():
				self.assertEqual(d.get(k), v)
