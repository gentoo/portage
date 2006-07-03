# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$


import commands,errno,os,re,shlex,sys
from portage_const import COLOR_MAP_FILE
from portage_util import writemsg
from portage_exception import PortageException, ParseError, PermissionDenied, FileNotFound

havecolor=1
dotitles=1

esc_seq = "\x1b["

g_attr = {}
g_attr["normal"]       =  0

g_attr["bold"]         =  1
g_attr["faint"]        =  2
g_attr["standout"]     =  3
g_attr["underline"]    =  4
g_attr["blink"]        =  5
g_attr["overline"]     =  6  # Why is overline actually useful?
g_attr["reverse"]      =  7
g_attr["invisible"]    =  8

g_attr["no-attr"]      = 22
g_attr["no-standout"]  = 23
g_attr["no-underline"] = 24
g_attr["no-blink"]     = 25
g_attr["no-overline"]  = 26
g_attr["no-reverse"]   = 27
# 28 isn't defined?
# 29 isn't defined?
g_attr["black"]        = 30
g_attr["red"]          = 31
g_attr["green"]        = 32
g_attr["yellow"]       = 33
g_attr["blue"]         = 34
g_attr["magenta"]      = 35
g_attr["cyan"]         = 36
g_attr["white"]        = 37
# 38 isn't defined?
g_attr["default"]      = 39
g_attr["bg_black"]     = 40
g_attr["bg_red"]       = 41
g_attr["bg_green"]     = 42
g_attr["bg_yellow"]    = 43
g_attr["bg_blue"]      = 44
g_attr["bg_magenta"]   = 45
g_attr["bg_cyan"]      = 46
g_attr["bg_white"]     = 47
g_attr["bg_default"]   = 49


# make_seq("blue", "black", "normal")
def color(fg, bg="default", attr=["normal"]):
	mystr = esc_seq[:] + "%02d" % g_attr[fg]
	for x in [bg]+attr:
		mystr += ";%02d" % g_attr[x]
	return mystr+"m"



codes={}
codes["reset"]     = esc_seq + "39;49;00m"

codes["bold"]      = esc_seq + "01m"
codes["faint"]     = esc_seq + "02m"
codes["standout"]  = esc_seq + "03m"
codes["underline"] = esc_seq + "04m"
codes["blink"]     = esc_seq + "05m"
codes["overline"]  = esc_seq + "06m"  # Who made this up? Seriously.

ansi_color_codes = []
for x in xrange(30, 38):
	ansi_color_codes.append("%im" % x)
	ansi_color_codes.append("%i;01m" % x)

rgb_ansi_colors = ['0x000000', '0x555555', '0xAA0000', '0xFF5555', '0x00AA00',
	'0x55FF55', '0xAA5500', '0xFFFF55', '0x0000AA', '0x5555FF', '0xAA00AA',
	'0xFF55FF', '0x00AAAA', '0x55FFFF', '0xAAAAAA', '0xFFFFFF']

for x in xrange(len(rgb_ansi_colors)):
	codes[rgb_ansi_colors[x]] = esc_seq + ansi_color_codes[x]

del x

codes["black"]     = codes["0x000000"]
codes["darkgray"]  = codes["0x555555"]

codes["red"]       = codes["0xFF5555"]
codes["darkred"]   = codes["0xAA0000"]

codes["green"]     = codes["0x55FF55"]
codes["darkgreen"] = codes["0x00AA00"]

codes["yellow"]    = codes["0xFFFF55"]
codes["brown"]     = codes["0xAA5500"]

codes["blue"]      = codes["0x5555FF"]
codes["darkblue"]  = codes["0x0000AA"]

codes["fuchsia"]   = codes["0xFF55FF"]
codes["purple"]    = codes["0xAA00AA"]

codes["turquoise"] = codes["0x55FFFF"]
codes["teal"]      = codes["0x00AAAA"]

codes["white"]     = codes["0xFFFFFF"]
codes["lightgray"] = codes["0xAAAAAA"]

codes["darkteal"]   = codes["turquoise"]
codes["darkyellow"] = codes["brown"]
codes["fuscia"]     = codes["fuchsia"]
codes["white"]      = codes["bold"]

# Colors from /sbin/functions.sh
codes["GOOD"]       = codes["green"]
codes["WARN"]       = codes["yellow"]
codes["BAD"]        = codes["red"]
codes["HILITE"]     = codes["teal"]
codes["BRACKET"]    = codes["blue"]

# Portage functions
codes["INFORM"] = codes["darkgreen"]
codes["UNMERGE_WARN"] = codes["red"]
codes["MERGE_LIST_PROGRESS"] = codes["yellow"]

def parse_color_map():
	myfile = COLOR_MAP_FILE
	ansi_code_pattern = re.compile("^[0-9;]*m$")
	def strip_quotes(token, quotes):
		if token[0] in quotes and token[0] == token[-1]:
			token = token[1:-1]
		return token
	try:
		s = shlex.shlex(open(myfile))
		s.wordchars = s.wordchars + ";" # for ansi codes
		d = {}
		while True:
			k, o, v = s.get_token(), s.get_token(), s.get_token()
			if k is s.eof:
				break
			if o != "=":
				raise ParseError("%s%s'%s'" % (s.error_leader(myfile, s.lineno), "expected '=' operator: ", o))
			k = strip_quotes(k, s.quotes)
			v = strip_quotes(v, s.quotes)
			if ansi_code_pattern.match(v):
				codes[k] = esc_seq + v
			else:
				if v in codes:
					codes[k] = codes[v]
				else:
					raise ParseError("%s%s'%s'" % (s.error_leader(myfile, s.lineno), "Undefined: ", v))
	except (IOError, OSError), e:
		if e.errno == errno.ENOENT:
			raise FileNotFound(myfile)
		elif e.errno == errno.EACCES:
			raise PermissionDenied(myfile)
		raise

try:
	parse_color_map()
except FileNotFound, e:
	pass
except PortageException, e:
	writemsg("%s\n" % str(e))

def nc_len(mystr):
	tmp = re.sub(esc_seq + "^m]+m", "", mystr);
	return len(tmp)

def xtermTitle(mystr):
	if havecolor and dotitles and os.environ.has_key("TERM") and sys.stderr.isatty():
		myt=os.environ["TERM"]
		legal_terms = ["xterm","Eterm","aterm","rxvt","screen","kterm","rxvt-unicode","gnome"]
		for term in legal_terms:
			if myt.startswith(term):
				sys.stderr.write("\x1b]0;"+str(mystr)+"\x07")
				sys.stderr.flush()
				break

default_xterm_title = None

def xtermTitleReset():
	global default_xterm_title
	if default_xterm_title is None:
		prompt_command = os.getenv('PROMPT_COMMAND')
		if prompt_command is not None:
			default_xterm_title = commands.getoutput(prompt_command)
		else:
			pwd = os.getenv('PWD','')
			home = os.getenv('HOME', '')
			if home != '' and pwd.startswith(home):
				pwd = '~' + pwd[len(home):]
			default_xterm_title = '%s@%s:%s' % (
				os.getenv('LOGNAME', ''), os.getenv('HOSTNAME', '').split('.', 1)[0], pwd)
	xtermTitle(default_xterm_title)

def notitles():
	"turn off title setting"
	dotitles=0

def nocolor():
	"turn off colorization"
	havecolor=0
	for x in codes.keys():
		codes[x]=""

def resetColor():
	return codes["reset"]

def colorize(color_key, text):
	return codes[color_key] + text + codes["reset"]

compat_functions_colors = ["bold","white","teal","turquoise","darkteal",
	"fuscia","fuchsia","purple","blue","darkblue","green","darkgreen","yellow",
	"brown","darkyellow","red","darkred"]

def create_color_func(color_key):
	def derived_func(*args):
		newargs = list(args)
		newargs.insert(0, color_key)
		return colorize(*newargs)
	return derived_func

for c in compat_functions_colors:
	setattr(sys.modules[__name__], c, create_color_func(c))
