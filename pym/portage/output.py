# Copyright 1998-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

__docformat__ = "epytext"

import commands, errno, os, re, shlex, sys, time
from portage.const import COLOR_MAP_FILE
from portage.util import writemsg
from portage.exception import PortageException, ParseError, PermissionDenied, FileNotFound

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

def xtermTitle(mystr, raw=False):
	if dotitles and "TERM" in os.environ and sys.stderr.isatty():
		myt=os.environ["TERM"]
		legal_terms = ["xterm","Eterm","aterm","rxvt","screen","kterm","rxvt-unicode","gnome"]
		for term in legal_terms:
			if myt.startswith(term):
				if not raw:
					mystr = "\x1b]0;%s\x07" % mystr
				sys.stderr.write(mystr)
				sys.stderr.flush()
				break

default_xterm_title = None

def xtermTitleReset():
	global default_xterm_title
	if default_xterm_title is None:
		prompt_command = os.getenv('PROMPT_COMMAND')
		if prompt_command == "":
			default_xterm_title = ""
		elif prompt_command is not None:
			default_xterm_title = commands.getoutput(prompt_command)
		else:
			pwd = os.getenv('PWD','')
			home = os.getenv('HOME', '')
			if home != '' and pwd.startswith(home):
				pwd = '~' + pwd[len(home):]
			default_xterm_title = '\x1b]0;%s@%s:%s\x07' % (
				os.getenv('LOGNAME', ''), os.getenv('HOSTNAME', '').split('.', 1)[0], pwd)
	xtermTitle(default_xterm_title, raw=True)

def notitles():
	"turn off title setting"
	dotitles=0

def nocolor():
	"turn off colorization"
	global havecolor
	havecolor=0

def resetColor():
	return codes["reset"]

def colorize(color_key, text):
	global havecolor
	if havecolor:
		return codes[color_key] + text + codes["reset"]
	else:
		return text

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
	globals()[c] = create_color_func(c)

def get_term_size():
	"""
	Get the number of lines and columns of the tty that is connected to
	stdout.  Returns a tuple of (lines, columns) or (-1, -1) if an error
	occurs. The curses module is used if available, otherwise the output of
	`stty size` is parsed.
	"""
	try:
		import curses
		curses.setupterm()
		return curses.tigetnum('lines'), curses.tigetnum('cols')
	except ImportError:
		pass
	st, out = commands.getstatusoutput('stty size')
	if st == os.EX_OK:
		out = out.split()
		if len(out) == 2:
			try:
				return int(out[0]), int(out[1])
			except ValueError:
				pass
	return -1, -1

class EOutput:
	"""
	Performs fancy terminal formatting for status and informational messages.

	The provided methods produce identical terminal output to the eponymous
	functions in the shell script C{/sbin/functions.sh} and also accept
	identical parameters.

	This is not currently a drop-in replacement however, as the output-related
	functions in C{/sbin/functions.sh} are oriented for use mainly by system
	init scripts and ebuilds and their output can be customized via certain
	C{RC_*} environment variables (see C{/etc/conf.d/rc}). B{EOutput} is not
	customizable in this manner since it's intended for more general uses.
	Likewise, no logging is provided.

	@ivar quiet: Specifies if output should be silenced.
	@type quiet: BooleanType
	@ivar term_columns: Width of terminal in characters. Defaults to the value
		specified by the shell's C{COLUMNS} variable, else to the queried tty
		size, else to C{80}.
	@type term_columns: IntType
	"""

	def __init__(self):
		self.__last_e_cmd = ""
		self.__last_e_len = 0
		self.quiet = False
		lines, columns = get_term_size()
		if columns <= 0:
			columns = 80
		# Adjust columns so that eend works properly on a standard BSD console.
		if os.environ.get("TERM") == "cons25":
			columns = columns - 1
		self.term_columns = columns

	def __eend(self, caller, errno, msg):
		if errno == 0:
			status_brackets = colorize("BRACKET", "[ ") + colorize("GOOD", "ok") + colorize("BRACKET", " ]")
		else:
			status_brackets = colorize("BRACKET", "[ ") + colorize("BAD", "!!") + colorize("BRACKET", " ]")
			if msg:
				if caller == "eend":
					self.eerror(msg[0])
				elif caller == "ewend":
					self.ewarn(msg[0])
		if self.__last_e_cmd != "ebegin":
			self.__last_e_len = 0
		print "%*s%s" % ((self.term_columns - self.__last_e_len - 6), "", status_brackets)
		sys.stdout.flush()

	def ebegin(self, msg):
		"""
		Shows a message indicating the start of a process.

		@param msg: A very brief (shorter than one line) description of the
			starting process.
		@type msg: StringType
		"""
		msg += " ..."
		if not self.quiet:
			self.einfon(msg)
		self.__last_e_len = len(msg) + 4
		self.__last_e_cmd = "ebegin"

	def eend(self, errno, *msg):
		"""
		Indicates the completion of a process, optionally displaying a message
		via L{eerror} if the process's exit status isn't C{0}.

		@param errno: A standard UNIX C{errno} code returned by processes upon
			exit.
		@type errno: IntType
		@param msg: I{(optional)} An error message, typically a standard UNIX
			error string corresponding to C{errno}.
		@type msg: StringType
		"""
		if not self.quiet:
			self.__eend("eend", errno, msg)
		self.__last_e_cmd = "eend"

	def eerror(self, msg):
		"""
		Shows an error message.

		@param msg: A very brief (shorter than one line) error message.
		@type msg: StringType
		"""
		if not self.quiet:
			if self.__last_e_cmd == "ebegin": print
			print colorize("BAD", " * ") + msg
			sys.stdout.flush()
		self.__last_e_cmd = "eerror"

	def einfo(self, msg):
		"""
		Shows an informative message terminated with a newline.

		@param msg: A very brief (shorter than one line) informative message.
		@type msg: StringType
		"""
		if not self.quiet:
			if self.__last_e_cmd == "ebegin": print
			print colorize("GOOD", " * ") + msg
			sys.stdout.flush()
		self.__last_e_cmd = "einfo"

	def einfon(self, msg):
		"""
		Shows an informative message terminated without a newline.

		@param msg: A very brief (shorter than one line) informative message.
		@type msg: StringType
		"""
		if not self.quiet:
			if self.__last_e_cmd == "ebegin": print
			print colorize("GOOD", " * ") + msg ,
			sys.stdout.flush()
		self.__last_e_cmd = "einfon"

	def ewarn(self, msg):
		"""
		Shows a warning message.

		@param msg: A very brief (shorter than one line) warning message.
		@type msg: StringType
		"""
		if not self.quiet:
			if self.__last_e_cmd == "ebegin": print
			print colorize("WARN", " * ") + msg
			sys.stdout.flush()
		self.__last_e_cmd = "ewarn"

	def ewend(self, errno, *msg):
		"""
		Indicates the completion of a process, optionally displaying a message
		via L{ewarn} if the process's exit status isn't C{0}.

		@param errno: A standard UNIX C{errno} code returned by processes upon
			exit.
		@type errno: IntType
		@param msg: I{(optional)} A warning message, typically a standard UNIX
			error string corresponding to C{errno}.
		@type msg: StringType
		"""
		if not self.quiet:
			self.__eend("ewend", errno, msg)
		self.__last_e_cmd = "ewend"

class ProgressBar(object):
	"""The interface is copied from the ProgressBar class from the EasyDialogs
	module (which is Mac only)."""
	def __init__(self, title=None, maxval=0, label=None):
		self._title = title
		self._maxval = maxval
		self._label = maxval
		self._curval = 0

	@property
	def curval(self):
		"""
		The current value (of type integer or long integer) of the progress
		bar. The normal access methods coerce curval between 0 and maxval. This
		attribute should not be altered directly.
		"""
		return self._curval

	@property
	def maxval(self):
		"""
		The maximum value (of type integer or long integer) of the progress
		bar; the progress bar (thermometer style) is full when curval equals
		maxval. If maxval is 0, the bar will be indeterminate (barber-pole).
		This attribute should not be altered directly.
		"""
		return self._maxval

	def title(self, newstr):
		"""Sets the text in the title bar of the progress dialog to newstr."""
		self._title = newstr

	def label(self, newstr):
		"""Sets the text in the progress box of the progress dialog to newstr."""
		self._label = newstr

	def set(self, value, maxval=None):
		"""
		Sets the progress bar's curval to value, and also maxval to max if the
		latter is provided. value is first coerced between 0 and maxval. The
		thermometer bar is updated to reflect the changes, including a change
		from indeterminate to determinate or vice versa.
		"""
		if maxval is not None:
			self._maxval = maxval
		if value < 0:
			value = 0
		elif value > self._maxval:
			value = self._maxval
		self._curval = value

	def inc(self, n=1):
		"""Increments the progress bar's curval by n, or by 1 if n is not
		provided. (Note that n may be negative, in which case the effect is a
		decrement.) The progress bar is updated to reflect the change. If the
		bar is indeterminate, this causes one ``spin'' of the barber pole. The
		resulting curval is coerced between 0 and maxval if incrementing causes
		it to fall outside this range.
		"""
		self.set(self._curval+n)

class TermProgressBar(ProgressBar):
	"""A tty progress bar similar to wget's."""
	def __init__(self, **kwargs):
		ProgressBar.__init__(self, **kwargs)
		lines, self.term_columns = get_term_size()
		self.file = sys.stdout
		self._min_columns = 11
		# for indeterminate mode, ranges from 0.0 to 1.0
		self._position = 0.0

	def set(self, value, maxval=None):
		ProgressBar.set(self, value, maxval=maxval)
		self._display_image(self._create_image())

	def _display_image(self, image):
		self.file.write('\r')
		self.file.write(image)
		self.file.flush()

	def _create_image(self):
		cols = self.term_columns
		min_columns = self._min_columns
		curval = self._curval
		maxval = self._maxval
		position = self._position
		if cols < 3:
			return ""
		bar_space = cols - 6
		if maxval == 0:
			max_bar_width = bar_space-3
			image = "    "
			if cols < min_columns:
				return image
			if position <= 0.5:
				offset = 2 * position
			else:
				offset = 2 * (1 - position)
			delta = 0.5 / max_bar_width
			position += delta
			if position >= 1.0:
				position = 0.0
			# make sure it touches the ends
			if 1.0 - position < delta:
				position = 1.0
			if position < 0.5 and 0.5 - position < delta:
				position = 0.5
			self._position = position
			bar_width = int(offset * max_bar_width)
			image = image + "[" + (bar_width * " ") + \
				"<=>" + ((max_bar_width - bar_width) * " ") + "]"
			return image
		else:
			max_bar_width = bar_space-1
			percentage = int(100 * float(curval) / maxval)
			if percentage == 100:
				percentage = 99
			image = ("%d%% " % percentage).rjust(4)
			if cols < min_columns:
				return image
			offset = float(curval) / maxval
			bar_width = int(offset * max_bar_width)
			image = image + "[" + (bar_width * "=") + \
				">" + ((max_bar_width - bar_width) * " ") + "]"
			return image
