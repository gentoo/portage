# Copyright 2010-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import tempfile

from portage import os
from portage import shutil
from portage import _unicode_encode
from portage.tests import TestCase
from portage.util import getconfig
from portage.exception import ParseError

class GetConfigTestCase(TestCase):
	"""
	Test that getconfig() produces that same result as bash would when
	sourcing the same input.
	"""

	_cases = {
		'FETCHCOMMAND'             : 'wget -t 3 -T 60 --passive-ftp -O "${DISTDIR}/${FILE}" "${URI}"',
		'FETCHCOMMAND_RSYNC'       : 'rsync -LtvP "${URI}" "${DISTDIR}/${FILE}"',
		'FETCHCOMMAND_SFTP'        : 'bash -c "x=\\${2#sftp://} ; host=\\${x%%/*} ; port=\\${host##*:} ; host=\\${host%:*} ; [[ \\${host} = \\${port} ]] && port= ; eval \\"declare -a ssh_opts=(\\${3})\\" ; exec sftp \\${port:+-P \\${port}} \\"\\${ssh_opts[@]}\\" \\"\\${host}:/\\${x#*/}\\" \\"\\$1\\"" sftp "${DISTDIR}/${FILE}" "${URI}" "${PORTAGE_SSH_OPTS}"',
		'FETCHCOMMAND_SSH'         : 'bash -c "x=\\${2#ssh://} ; host=\\${x%%/*} ; port=\\${host##*:} ; host=\\${host%:*} ; [[ \\${host} = \\${port} ]] && port= ; exec rsync --rsh=\\"ssh \\${port:+-p\\${port}} \\${3}\\" -avP \\"\\${host}:/\\${x#*/}\\" \\"\\$1\\"" rsync "${DISTDIR}/${FILE}" "${URI}" "${PORTAGE_SSH_OPTS}"',
		'PORTAGE_ELOG_MAILSUBJECT' : '[portage] ebuild log for ${PACKAGE} on ${HOST}'
	}

	def testGetConfig(self):
		make_globals_file = os.path.join(self.cnf_path, "make.globals")
		d = getconfig(make_globals_file)
		for k, v in self._cases.items():
			self.assertEqual(d[k], v)

	def testGetConfigSourceLex(self):
		try:
			tempdir = tempfile.mkdtemp()
			make_conf_file = os.path.join(tempdir, 'make.conf')
			with open(make_conf_file, 'w') as f:
				f.write('source "${DIR}/sourced_file"\n')
			sourced_file = os.path.join(tempdir, 'sourced_file')
			with open(sourced_file, 'w') as f:
				f.write('PASSES_SOURCING_TEST="True"\n')

			d = getconfig(make_conf_file, allow_sourcing=True, expand={"DIR": tempdir})

			# PASSES_SOURCING_TEST should exist in getconfig result.
			self.assertTrue(d is not None)
			self.assertEqual("True", d['PASSES_SOURCING_TEST'])

			# With allow_sourcing=True and empty expand map, this should
			# throw a FileNotFound exception.
			self.assertRaisesMsg("An empty expand map should throw an exception",
				ParseError, getconfig, make_conf_file, allow_sourcing=True, expand={})
		finally:
			shutil.rmtree(tempdir)

	def testGetConfigProfileEnv(self):
		# Test the mode which is used to parse /etc/env.d and /etc/profile.env.

		cases = {
			'LESS_TERMCAP_mb': r"$\E[01;31m", # bug #410625
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
