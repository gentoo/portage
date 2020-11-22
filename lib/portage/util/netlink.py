# Copyright 2019-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

from io import BytesIO
from os import strerror
from struct import Struct

import socket
from socket import (
	AF_NETLINK, AF_UNSPEC,
	NETLINK_ROUTE,
	SOCK_DGRAM,
	inet_pton,
)

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

nlmsghdr = Struct('=IHHII')
nlmsgerr = Struct('i')
rtattr = Struct('HH')
ifinfomsg = Struct('BHiII')
ifaddrmsg = Struct('BBBBi')

def create_nlmsg(nlmsg_type, nlmsg_flags, nlmsg_seq, nlmsg_pid, data):
	nlmsg_len = nlmsghdr.size + len(data)
	return nlmsghdr.pack(nlmsg_len, nlmsg_type, nlmsg_flags, nlmsg_seq, nlmsg_pid) + data

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
		self.addr = (0, 0)
		try:
			self.sock.bind(self.addr)
		except socket.error:
			self.sock.close()
			raise

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		self.sock.close()

	def send_message(self, msg):
		self.sock.sendto(msg, self.addr)
		# Messages are variable length, but 128 is enough for the ones we care about.
		resp = self.sock.recv(128)
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
		flags = NLM_F_REQUEST|NLM_F_ACK
		msg = create_nlmsg(RTM_NEWLINK, flags, 1, 0, body)
		self.send_message(msg)

	def add_address(self, ifindex, family, address, prefixlen):
		body = ifaddrmsg.pack(family, prefixlen, 0, 0, ifindex)
		addr = inet_pton(family, address)
		body += create_rtattr(IFA_LOCAL, addr)
		flags = NLM_F_REQUEST|NLM_F_ACK|NLM_F_EXCL|NLM_F_CREATE
		msg = create_nlmsg(RTM_NEWADDR, flags, 1, 0, body)
		self.send_message(msg)
