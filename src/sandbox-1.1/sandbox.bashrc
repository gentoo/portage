# Copyright (C) 2001 Geert Bevin, Uwyn, http://www.uwyn.com
# Distributed under the terms of the GNU General Public License, v2 or later 
# Author : Geert Bevin <gbevin@uwyn.com>
# $Header: /var/cvsroot/gentoo-src/portage/src/sandbox-1.1/Attic/sandbox.bashrc,v 1.2.4.1 2004/10/22 16:53:30 carpaski Exp $
source /etc/profile
export LD_PRELOAD="$SANDBOX_LIB"
alias make="make LD_PRELOAD=$SANDBOX_LIB"
alias su="su -c '/bin/bash -rcfile $SANDBOX_DIR/sandbox.bashrc'"
