
import os.path
import subprocess
import sys
import time

try:
	import portage.const
	import portage.proxy as proxy
	from portage import _encodings, _shell_quote, _unicode_encode, _unicode_decode
	from portage.const import PORTAGE_BASE_PATH, BASH_BINARY
except ImportError as e:
	sys.stderr.write("\n\n")
	sys.stderr.write("!!! Failed to complete portage imports. There are internal modules for\n")
	sys.stderr.write("!!! portage and failure here indicates that you have a problem with your\n")
	sys.stderr.write("!!! installation of portage. Please try a rescue portage located in the ebuild\n")
	sys.stderr.write("!!! repository under '/var/db/repos/gentoo/sys-apps/portage/files/' (default).\n")
	sys.stderr.write("!!! There is a README.RESCUE file that details the steps required to perform\n")
	sys.stderr.write("!!! a recovery of portage.\n")
	sys.stderr.write("    "+str(e)+"\n\n")
	raise


VERSION = "HEAD"

REPOMAN_BASE_PATH = os.path.join(os.sep, os.sep.join(os.path.realpath(__file__.rstrip("co")).split(os.sep)[:-3]))

_not_installed = os.path.isfile(os.path.join(REPOMAN_BASE_PATH, ".repoman_not_installed"))

if VERSION == 'HEAD':
	class _LazyVersion(proxy.objectproxy.ObjectProxy):
		def _get_target(self):
			global VERSION
			if VERSION is not self:
				return VERSION
			if os.path.isdir(os.path.join(PORTAGE_BASE_PATH, '.git')):
				encoding = _encodings['fs']
				cmd = [BASH_BINARY, "-c", ("cd %s ; git describe  --match 'repoman-*' || exit $? ; " + \
					"if [ -n \"`git diff-index --name-only --diff-filter=M HEAD`\" ] ; " + \
					"then echo modified ; git rev-list --format=%%ct -n 1 HEAD ; fi ; " + \
					"exit 0") % _shell_quote(PORTAGE_BASE_PATH)]
				cmd = [_unicode_encode(x, encoding=encoding, errors='strict')
					for x in cmd]
				proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT)
				output = _unicode_decode(proc.communicate()[0], encoding=encoding)
				status = proc.wait()
				if os.WIFEXITED(status) and os.WEXITSTATUS(status) == os.EX_OK:
					output_lines = output.splitlines()
					if output_lines:
						version_split = output_lines[0].split('-')
						if len(version_split) > 1:
							VERSION = version_split[1]
							patchlevel = False
							if len(version_split) > 2:
								patchlevel = True
								VERSION = "%s_p%s" % (VERSION, version_split[2])
							if len(output_lines) > 1 and output_lines[1] == 'modified':
								head_timestamp = None
								if len(output_lines) > 3:
									try:
										head_timestamp = int(output_lines[3])
									except ValueError:
										pass
								timestamp = int(time.time())
								if head_timestamp is not None and timestamp > head_timestamp:
									timestamp = timestamp - head_timestamp
								if not patchlevel:
									VERSION = "%s_p0" % (VERSION,)
								VERSION = "%s_p%d" % (VERSION, timestamp)
							return VERSION
					else:
						print("NO output lines :(")
			VERSION = 'HEAD'
			return VERSION
	VERSION = _LazyVersion()
