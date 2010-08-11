# Copyright 2010 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

from __future__ import print_function

import errno
import shutil
import warnings

import portage
from portage import os, _encodings, _unicode_decode, _unicode_encode
from portage.data import portage_gid, portage_uid
from portage.dep import dep_getkey
from portage.localization import _
from portage.manifest import Manifest
from portage.util import writemsg, writemsg_stdout
