# elog/mod_mail_summary.py - elog dispatch module
# Copyright 2006-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage
from portage.exception import AlarmSignal, PortageException
from portage.localization import _
from portage.util import writemsg
from portage import _encodings
from portage import _unicode_decode

import socket
import time

_config_keys = (
    "PORTAGE_ELOG_MAILURI",
    "PORTAGE_ELOG_MAILFROM",
    "PORTAGE_ELOG_MAILSUBJECT",
)
_items = {}


def process(mysettings, key, logentries, fulltext):
    global _items
    time_str = _unicode_decode(
        time.strftime("%Y%m%d-%H%M%S %Z", time.localtime(time.time())),
        encoding=_encodings["content"],
        errors="replace",
    )
    header = _(
        ">>>> Messages generated for package %(pkg)s by process %(pid)d on %(time)s:\n\n"
    ) % {"pkg": key, "pid": portage.getpid(), "time": time_str}
    config_root = mysettings["PORTAGE_CONFIGROOT"]

    # Copy needed variables from the config instance,
    # since we don't need to hold a reference for the
    # whole thing. This also makes it possible to
    # rely on per-package variable settings that may
    # have come from /etc/portage/package.env, since
    # we'll be isolated from any future mutations of
    # mysettings.
    config_dict = {}
    for k in _config_keys:
        v = mysettings.get(k)
        if v is not None:
            config_dict[k] = v

    config_dict, items = _items.setdefault(config_root, (config_dict, {}))
    items[key] = header + fulltext


def finalize():
    global _items
    for mysettings, items in _items.values():
        _finalize(mysettings, items)
    _items.clear()


def _finalize(mysettings, items):
    if len(items) == 0:
        return
    if len(items) == 1:
        count = _("one package")
    else:
        count = _("multiple packages")
    if "PORTAGE_ELOG_MAILURI" in mysettings:
        myrecipient = mysettings["PORTAGE_ELOG_MAILURI"].split()[0]
    else:
        myrecipient = "root@localhost"

    myfrom = mysettings.get("PORTAGE_ELOG_MAILFROM", "")
    myfrom = myfrom.replace("${HOST}", socket.getfqdn())
    mysubject = mysettings.get("PORTAGE_ELOG_MAILSUBJECT", "")
    mysubject = mysubject.replace("${PACKAGE}", count)
    mysubject = mysubject.replace("${HOST}", socket.getfqdn())

    mybody = _(
        "elog messages for the following packages generated by "
        "process %(pid)d on host %(host)s:\n"
    ) % {"pid": portage.getpid(), "host": socket.getfqdn()}
    for key in items:
        mybody += f"- {key}\n"

    mymessage = portage.mail.create_message(
        myfrom, myrecipient, mysubject, mybody, attachments=list(items.values())
    )

    # Timeout after one minute in case send_mail() blocks indefinitely.
    try:
        try:
            AlarmSignal.register(60)
            portage.mail.send_mail(mysettings, mymessage)
        finally:
            AlarmSignal.unregister()
    except AlarmSignal:
        writemsg(
            "Timeout in finalize() for elog system 'mail_summary'\n", noiselevel=-1
        )
    except PortageException as e:
        writemsg(f"{e}\n", noiselevel=-1)

    return
