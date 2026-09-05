# Copyright 2019-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import socket
from io import BytesIO
from os import strerror
from socket import (
    AF_NETLINK,
    AF_UNSPEC,
    MSG_PEEK,
    MSG_TRUNC,
    NETLINK_ROUTE,
    SOCK_DGRAM,
    inet_pton,
)
from struct import Struct

IFA_LOCAL = 2
IFF_UP = 0x1
IFLA_IFNAME = 3
NLMSG_ERROR = 2
RTM_NEWLINK = 16
RTM_GETLINK = 18
RTM_NEWADDR = 20
NLM_F_REQUEST = 0x1
NLM_F_ACK = 0x4
NLM_F_EXCL = 0x200
NLM_F_CREATE = 0x400

nlmsghdr = Struct("=IHHII")
nlmsgerr = Struct("i")
rtattr = Struct("HH")
ifinfomsg = Struct("BHiII")
ifaddrmsg = Struct("BBBBI")


def create_nlmsg(nlmsg_type, nlmsg_flags, nlmsg_seq, nlmsg_pid, data):
    nlmsg_len = nlmsghdr.size + len(data)
    return (
        nlmsghdr.pack(nlmsg_len, nlmsg_type, nlmsg_flags, nlmsg_seq, nlmsg_pid) + data
    )


def create_rtattr(rta_type, data):
    rta_len = rtattr.size + len(data)
    return rtattr.pack(rta_len, rta_type) + data


def parse_message(msg):
    buf = BytesIO(msg)
    hdr = nlmsghdr.unpack(buf.read(nlmsghdr.size))
    if hdr[1] == NLMSG_ERROR:
        err = nlmsgerr.unpack(buf.read(nlmsgerr.size))
        error = -err[0]
        if error != 0:
            raise OSError(error, strerror(error))
    elif hdr[1] == RTM_NEWLINK:
        # kernel responds to RTM_GETLINK with RTM_NEWLINK.
        # We only care about the ifindex for get_link_ifindex.
        return ifinfomsg.unpack(buf.read(ifinfomsg.size))


class RtNetlink:
    def __init__(self):
        self.sock = socket.socket(AF_NETLINK, SOCK_DGRAM, NETLINK_ROUTE)
        try:
            addr = (0, 0)
            self.sock.bind(addr)
            self.sock.connect(addr)
        except OSError:
            self.sock.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.sock.close()

    def send_message(self, msg):
        self.sock.send(msg)

        # The kernel docs say 8kB is a good buffer size.
        # https://docs.kernel.org/7.2/userspace-api/netlink/intro.html#buffer-sizing
        # Use MSG_PEEK|MSG_TRUNC to get the actual size in case the kernel changes.
        resp = self.sock.recv(8192, MSG_PEEK | MSG_TRUNC)

        # socket.recv() uses the passed size when allocating its buffer.
        # It resizes the buffer based on the return value of the syscall.
        resp = self.sock.recv(len(resp))

        return parse_message(resp)

    def get_link_ifindex(self, ifname):
        body = ifinfomsg.pack(AF_UNSPEC, 0, 0, 0, 0)
        body += create_rtattr(IFLA_IFNAME, ifname)
        flags = NLM_F_REQUEST
        msg = create_nlmsg(RTM_GETLINK, flags, 1, 0, body)
        resp = self.send_message(msg)
        return resp[2]

    def set_link_up(self, ifindex):
        body = ifinfomsg.pack(AF_UNSPEC, 0, ifindex, IFF_UP, IFF_UP)
        flags = NLM_F_REQUEST | NLM_F_ACK
        msg = create_nlmsg(RTM_NEWLINK, flags, 1, 0, body)
        self.send_message(msg)

    def add_address(self, ifindex, family, address, prefixlen):
        body = ifaddrmsg.pack(family, prefixlen, 0, 0, ifindex)
        addr = inet_pton(family, address)
        body += create_rtattr(IFA_LOCAL, addr)
        flags = NLM_F_REQUEST | NLM_F_ACK | NLM_F_EXCL | NLM_F_CREATE
        msg = create_nlmsg(RTM_NEWADDR, flags, 1, 0, body)
        self.send_message(msg)
