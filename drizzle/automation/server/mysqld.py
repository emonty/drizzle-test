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

"""Defines the adapter for controlling a MySQL database server"""

import os
import commands
from drizzle.automation.lib  import logging
import sys
import time

"""A class responsible for starting, stopping, and pinging a MySQL server"""
class MySQLdServer:

  def __init__(self, basedir, start_options= {}):
    self._basedir= basedir
    self._datadir= os.path.join(basedir, "var")
    # We default to port 9306 if not specified...
    if "port" not in start_options.keys():
      self._port= 10000
    else:
      self._port= int(start_options["port"])

    # A profiler tool, if any.
    self._profiler= None

    self.setStartOptions(start_options)

  def setStartOptions(self, start_options):
    self._start_options= start_options

  def setProfiler(self, profiler):
    self._profiler= profiler

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
    """Starts a MySQLd server with startup options.  If options are supplied, 
those are used, else the stored startup options (set with setStartupOptions()) 
are used."""

    start_option_string= self.getStartOptionString()
    if self._profiler is not None:
      start_cmd= self._profiler.getStartCmdPrefix() + " "
    else:
      start_cmd= ""
    start_cmd= start_cmd + "%s --no-defaults --port=%d --basedir=%s --datadir=%s --language=%s --log-error=%s %s &" % (
                                                                  os.path.join(self._basedir, "bin", "mysqld")
                                                                , self._port
                                                                , self._basedir
                                                                , self._datadir
                                                                , os.path.join(self._basedir, "share", "english")
                                                                , os.path.join(self._datadir, "error.log")
                                                                , start_option_string
                                                                  )

    logging.info("Starting MySQL server on port %d" % self._port)
    server_output= os.system(start_cmd)

    # Here, we sleep until the server is up and running or until a timeout occurs...
    if self._profiler is not None:
      timeout= 20
    else:
      timeout= 10
    timer= 0
    while not self.ping(quiet= True) and timer != timeout:
      time.sleep(1)
      timer= timer + 1

  def ping(self, quiet= False):
    """Pings the server. Returns True if server is up and running, False otherwise."""
    ping_cmd= "%s --no-defaults --user=root --port=%d ping" % (os.path.join(self._basedir, "bin", "mysqladmin"), self._port)

    if not quiet:
      logging.info("Pinging MySQL server on port %d" % self._port)
    (retcode, output)= commands.getstatusoutput(ping_cmd)

    return retcode == 0

  def bootstrap(self):
    """Starts up a bootstrap version of the MySQL server in a local datadir exactly how
the MySQL Test Suite bootstraps its server.  This is necessary because of the absolute
hell you go through with trying to use the mysql_install_db script when you have not run
make install (which we don't want to do...)"""

    # Create the mysql "database" directory
    (retcode, output)= commands.getstatusoutput("mkdir -p %s" % os.path.join(self._datadir, "mysql"))

    # Before we bootstrap, we need to write the bootstrap SQL file
    # which is passed to the server on startup....
    bootstrap_sql_filename= "/tmp/bootstrap.sql"
    bootstrap_sql_file= open(bootstrap_sql_filename, "w")

    bootstrap_sql_file.write("use mysql")

    # Add the system tables...
    system_tables_filename= os.path.join(self._basedir, "share", "mysql_system_tables.sql")
    bootstrap_sql_file.write(open(system_tables_filename).read())

    # Add the data for the system tables...
    system_tables_data_filename= os.path.join(self._basedir, "share", "mysql_system_tables_data.sql")
    bootstrap_sql_file.write(open(system_tables_data_filename).read())

    # Add the timezone minimum data
    timezone_tables_sql_filename= os.path.join(self._basedir, "share", "mysql_test_data_timezone.sql")
    bootstrap_sql_file.write(open(timezone_tables_sql_filename).read())
    bootstrap_sql_file.close()

    start_option_string= self.getStartOptionString()

    logging.info("Bootstrapping MySQL server on port %d" % self._port)
    start_cmd= "%s --no-defaults --port=%d --bootstrap --basedir=%s --datadir=%s --language=%s --log-error=%s %s < %s &" % (
                                                                  os.path.join(self._basedir, "bin", "mysqld")
                                                                , self._port
                                                                , self._basedir
                                                                , self._datadir
                                                                , os.path.join(self._basedir, "share", "english")
                                                                , os.path.join(self._datadir, "error.log")
                                                                , start_option_string
                                                                , bootstrap_sql_filename
                                                                  )

    server_output= os.system(start_cmd)

    time.sleep(5)

    if self.ping(quiet= True):
      self.stop()
    
    # Delete our bootstrapping file
    os.unlink(bootstrap_sql_filename)

  def clear(self):
    """Clears data files for the server."""
    logging.info("Clearing MySQL server on port %d" % self._port)
    
    (retcode, output)= commands.getstatusoutput("rm -rf %s && mkdir -p %s" % (self._datadir, self._datadir))
    
    if retcode != 0:
      logging.error("Failed to clear MySQL datadir %s...Got:\n%s" % (self._datadir, output))
      sys.exit(1)

    self.bootstrap()

  def stop(self):
    """Stops the server"""
    stop_cmd= "%s --no-defaults --user=root --port=%d shutdown" % (os.path.join(self._basedir, "bin", "mysqladmin"), self._port)

    logging.info("Stopping MySQL server on port %d" % self._port)
    (retcode, output)= commands.getstatusoutput(stop_cmd)

    if retcode != 0:
      logging.error("Failed to stop MySQL server...Got:\n%s" % output)
      sys.exit(1)

  def restart(self, start_options= None):
    self.stop()
    self.start(start_options)

  def stopAll(self):
    """Stops ALL MySQL servers except the local one..."""
    return
  #logging.info("Stopping all MySQL servers.")
  #  (retcode, num_drizzled_running)= commands.getstatusoutput("ps aux | grep mysqld | wc -l")
  #  if retcode == 0 and int(num_drizzled_running) > 0:
    #    (retcode, ignored)= commands.getstatusoutput("killall -9 mysqld")
    #  time.sleep(3)

