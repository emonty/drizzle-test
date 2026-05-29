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
from drizzle.automation.lib  import logging
import sys
import time

"""A class responsible for starting, stopping, and pinging a Drizzled server"""
class DrizzledServer:

  def __init__(self, basedir, start_options= {}):
    self._basedir= basedir

    # We default to basedir/var for datadir,
    # however, there are cases where we want multiple servers spun up
    # and it makes sense to create new datadirs.  We provide the value
    # as a subdir of basedir.  This allows for basedir/var basedir/var1..
    if "datadir" not in start_options.keys():
      self._datadir= os.path.join(basedir, "var")
    else:
      self._datadir= os.path.join(basedir,start_options["datadir"])

    # We default to port 9306 if not specified...
    if "port" not in start_options.keys():
      self._port= 9306
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
    # We ignore some options as they are already directly incorporated
    # into the server start command.  Using them here equals a failed
    # start
    ignored_options= ['datadir','port']
    for key in self._start_options.keys(): 
      if key not in ignored_options:
        # Ensure option names are output as --option_name
        tmp_key= key
        if not key.startswith("--"):
          tmp_key= "--" + tmp_key
          tmp_key= tmp_key.replace("_","-")
        if self._start_options[key] == 'option_flag': 
          # we have an option_flag, nothing to set
          # such as --core-file
          options.append(tmp_key)
        else:
          options.append("%s=%s" % (tmp_key, self._start_options[key]))

    return " ".join(options)

  def crash_check(self):
    executable = os.path.join(self._basedir,"drizzled/.libs/lt-drizzled")
    core_file = os.path.join(self._datadir, "core")
    gdb_cmd_file = "/etc/drizzle-automation/gdb/backtrace.gdb"
     
    # Are we still running?
    if not self.ping(quiet= True):
      logging.info("WARNING:  Server not running.  Checking for core file.")
      # Check for core file
      if os.path.isfile(core_file):
        logging.info("Core file found.  Attempting to produce a backtrace.")
        if os.path.isfile(gdb_cmd_file):
          gdb_cmd = "gdb --batch -se=%s --core=%s --command=%s" %(executable, core_file, gdb_cmd_file)
          gdb_retcode, gdb_output= commands.getstatusoutput(gdb_cmd)
          if gdb_output:
            logging.info("%s" %(gdb_output)) 
          else:
            logging.info("No output from gdb commmand %s" %(gdb_cmd)) 
        else:
          logging.info("ERROR:  gdb command file %s not found, cannot get backtrace" %(gdb_cmd_file)) 
      else:  # server= stopped, but no core found in var
        logging.info("ERROR:  Core file %s not found" %(core_file)) 
        self.dump_error_log()
      return 1
    else:
      logging.info("Server still running / not crashed")  
      return 0

  def dump_error_log(self):
    """Print contents of drizzled error log"""
    logging.info("Dumping error log...")
    infilename= os.path.join(self._basedir,"error.log")
    inf= open(infilename,"r+b")
    inlines= inf.readlines()
    for inline in inlines:
      logging.info(inline.strip())
    inf.close()

  def option_dot_test(self):
    cmd = "%s --help | grep mysql-protocol[.]port" %(os.path.join(self._basedir,"drizzled", "drizzled"))
    retcode,output = commands.getstatusoutput(cmd)
    if output:
      return True
    else:
      return False

  def start(self):
    """Starts a Drizzled server with startup options.  If options are supplied, 
those are used, else the stored startup options (set with setStartupOptions()) 
are used."""
    start_option_string= self.getStartOptionString()
    if self._profiler is not None:
      start_cmd= self._profiler.getStartCmdPrefix() + " "
    else:
      start_cmd= ""
    # We have introduced a new style of plugin options
    # Moving forward, we will have things like mysql-protocol.port
    # vs. mysql-protocol-port.  We grep the server help to see
    # which delimiter to choose 1= ., 0= -
    if self.option_dot_test():
      option_delimiter = '.'
    else:
      option_delimiter = '-'
    start_cmd= start_cmd + "%s --core-file --mysql-protocol%sport=%d --drizzle-protocol%sport=%d --basedir=%s --datadir=%s %s > error.log 2>&1 &" % (os.path.join(self._basedir, "drizzled", "drizzled")
                                                                , option_delimiter
                                                                , self._port
                                                                , option_delimiter
                                                                , self._port+10 
                                                                , self._basedir
                                                                , self._datadir
                                                                , start_option_string)

    logging.info("Starting Drizzled server on port %d" % self._port)
    logging.info("PWD:  %s" % (os.getcwd()))
    server_output= os.system(start_cmd)
    # Here, we sleep until the server is up and running or until a timeout occurs...
    if self._profiler is not None:
      timeout= 70
    else:
      timeout= 60
    timer= 0
    while not self.ping(quiet= True) and timer != timeout:
      time.sleep(1)
      timer= timer + 1
    # We make sure the server is running and return False if not 
    if timer == timeout and not self.ping(quiet= True):
      logging.error(( "Server failed to start within %d seconds.  This could be a problem with the test machine or the server itself" %(timeout)))
      self.crash_check()
      return False
    return True

  def ping(self, quiet= False):
    """Pings the server. Returns True if server is up and running, False otherwise."""
    ping_cmd= "%s -uroot --ping --port=%d" % (os.path.join(self._basedir, "client", "drizzle"), self._port)

    if not quiet:
      logging.info("Pinging Drizzled server on port %d" % self._port)
    (retcode, output)= commands.getstatusoutput(ping_cmd)

    return retcode == 0

  def clear(self):
    """Clears data files for the server."""
    logging.info("Clearing Drizzled server on port %d" % self._port)
    (retcode, ignored)= commands.getstatusoutput("rm -rf %s; mkdir -p %s" % (self._datadir, self._datadir))

  def stop(self):
    """Stops the server"""
    stop_cmd= "%s -uroot --shutdown --port=%d" % (os.path.join(self._basedir, "client", "drizzle"), self._port)

    logging.info("Stopping Drizzled server on port %d" % self._port)
    (retcode, output)= commands.getstatusoutput(stop_cmd)

    if retcode != 0:
      logging.error("Failed to stop Drizzled server. Error code = %d  Error log:\n" % (retcode))
      self.dump_error_log()
      sys.exit(1)

  def restart(self, start_options= None):
    self.stop()
    self.start(start_options)

  def stopAll(self):
    """Stops ALL drizzled servers"""
    logging.info("Stopping all Drizzle servers.")
    (retcode, num_drizzled_running)= commands.getstatusoutput("ps aux | grep drizzled | wc -l")
    if retcode == 0 and int(num_drizzled_running) > 0:
      # when running drizzle from the workspace the process is actually running as lt-drizzled
      (retcode, ignored)= commands.getstatusoutput("killall -9 lt-drizzled")
      time.sleep(3)
