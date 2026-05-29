#! /usr/bin/python
# -*- mode: c; c-basic-offset: 2; indent-tabs-mode: nil; -*-
# vim:expandtab:shiftwidth=2:tabstop=2:smarttab:
#
# Copyright (C) 2009 Sun Microsystems
#
# Authors:
#
#  Jay Pipes <joinfu@sun.com>
#
# This file is part of the Drizzle Automation Project.
#
# The Drizzle Automation Project is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation.
#
# The Drizzle Automation Project is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with The Drizzle Automation Project (see COPYING.LESSER). If not, 
# see <http://www.gnu.org/licenses/>.

"""Defines the adapter for controlling a Drizzle database server"""

import os
import commands
from drizzle.automation.lib import logging
import sys

"""A class responsible for building a Drizzled server in a BZR branch."""
class DrizzledBzrBuilder:

  def __init__(self, builddir, configure_options= "", make_options= "-j2"):
    self._builddir= builddir
    self._configure_options= configure_options
    self._make_options= make_options

  def clean(self):
    """Make cleans the drizzled source"""
    clean_cmd= "make clean"
    # Ignore the output. If it can't clean, it's likely b/c it's a fresh branch....
    (retcode, ignored)= commands.getstatusoutput(clean_cmd)

  def build(self, force_rebuild= False):
    """Configures and builds a Drizzled server in a BZR branch directory."""
    reconfigure_cmd= "./config/autorun.sh && ./configure %s" % self._configure_options
    configure_cmd= "configure %s" % self._configure_options
    make_cmd= "make %s" % self._make_options

    os.chdir(self._builddir)

    if force_rebuild is True:
      self.clean()

      logging.info("Reconfiguring Drizzled server with %s" % reconfigure_cmd)
      
      # Reconfigure and re-set autotools
      (retcode, output)= commands.getstatusoutput(reconfigure_cmd)

      if not retcode == 0:
        logging.error("Failed to reconfigure...Got:\n%s" % output)
        sys.exit(1)

    logging.info("Making Drizzled server with %s" % self._make_options)

    (retcode, ignored)= commands.getstatusoutput(make_cmd)

    if not retcode == 0:
      self.clean()

      logging.info("Configuring Drizzled server with %s" % self._configure_options)

      (retcode, output)= commands.getstatusoutput(reconfigure_cmd)

      if not retcode == 0:
        logging.error("Failed to configure...Got:\n%s" % output)
        sys.exit(1)

      # Try building the server again...
      logging.info("Making Drizzled server with %s" % self._make_options)

      (retcode, output)= commands.getstatusoutput(make_cmd)

      if not retcode == 0:
        logging.error("Failed to build server...Got:\n%s" % output)
        sys.exit(1)
