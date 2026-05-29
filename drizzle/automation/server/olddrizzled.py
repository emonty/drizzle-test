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

"""Defines the adapter for controlling a Drizzle database server prior to r950 when the drizzleadmin tool was removed."""

import os
import commands
from drizzle.automation.lib  import logging
import sys
import time

"""A class responsible for starting, stopping, and pinging a Drizzled server"""
class DrizzledServer:

  def __init__(self, basedir, start_options= {}):
    self._basedir= basedir
    self._datadir= os.path.join(basedir, "var")
    # We default to port 9306 if not specified...
    if "port" not in start_options.keys():
      self._port= 9306
    else:
      self._port= int(start_options["port"])

    self.setStartOptions(start_options)

  def setStartOptions(self, start_options):
    self._start_options= start_options

  def getPort(self):
    """Returns default port, or supplied port from configuration options"""
    return self._port

  def getStartOptionString(self):
    """Builds the string of options to pass to drizzled on startup"""
    options= []
    for key in self._start_options.keys():
      # Ensure option names are output as --option_name
      tmp_key= key
      if not key.startswith("--"):
        tmp_key= "--" + tmp_key.replace('-','_')
      else:
        tmp_key= "--" + tmp_key[2:].replace("-","_")
      options.append("%s=%s" % (tmp_key, self._start_options[key]))

    return " ".join(options)

  def start(self):
    """Starts a Drizzled server with startup options.  If options are supplied, 
those are used, else the stored startup options (set with setStartupOptions()) 
are used."""
    start_option_string= self.getStartOptionString()
    start_cmd= "%s --port=%d --basedir=%s --datadir=%s %s &" % (os.path.join(self._basedir, "drizzled", "drizzled")
                                                                , self._port
                                                                , self._basedir
                                                                , self._datadir
                                                                , start_option_string)

    logging.info("Starting Drizzled server on port %d with options:\n%s" % (self._port, start_option_string))
    server_output= os.system(start_cmd)

    time.sleep(6)

    # Here, we sleep until the server is up and running or until a timeout occurs...
    timeout= 10
    timer= 0
    while not self.ping(quiet= True) and timer != timeout:
      time.sleep(1)
      timer= timer + 1

  def ping(self, quiet= False):
    """Pingss the server. Returns True if server is up and running, False otherwise."""
    ping_cmd= "%s --port=%d --user=root ping" % (os.path.join(self._basedir, "client", "drizzleadmin"), self._port)

    if not quiet:
      logging.info("Pinging Drizzled server on port %d" % self._port)
    (retcode, output)= commands.getstatusoutput(ping_cmd)

    return retcode == 0

  def clear(self):
    """Clears data files for the server."""
    logging.info("Clearing Drizzled server on port %d datadir" % self._port)
    (retcode, ignored)= commands.getstatusoutput("rm -rf %s; mkdir -p %s" % (self._datadir, self._datadir))

  def stop(self):
    """Stops the server"""
    stop_cmd= "%s --port=%d --user=root shutdown" % (os.path.join(self._basedir, "client", "drizzleadmin"), self._port)

    logging.info("Stopping Drizzled server on port %d" % self._port)
    (retcode, output)= commands.getstatusoutput(stop_cmd)

    if retcode != 0:
      logging.error("Failed to stop Drizzled server...Got:\n%s" % output)
      sys.exit(1)

  def restart(self, start_options= None):
    self.stop()
    self.start(start_options)

  def stopAll(self):
    """Stops ALL drizzled servers"""
    logging.info("Stopping all Drizzle servers.")
    (retcode, num_drizzled_running)= commands.getstatusoutput("ps aux | grep lt-drizzled | wc -l")
    if retcode == 0 and int(num_drizzled_running) > 0:
      (retcode, ignored)= commands.getstatusoutput("killall -9 lt-drizzled")
      time.sleep(4)
