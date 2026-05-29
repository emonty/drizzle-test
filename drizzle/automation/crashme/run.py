#! /usr/bin/python
# -*- mode: c; c-basic-offset: 2; indent-tabs-mode: nil; -*-
# vim:expandtab:shiftwidth=2:tabstop=2:smarttab:
#
# Copyright (C) 2009 Sun Microsystems
#
# Authors:
#
#  Jay Pipes <joinfu@sun.com>
#  Lee Bieber <lee.bieber@sun.com>
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

"""Script to automate running and processing of benchmarks."""

import sys
import socket
import os
import os.path
from drizzle.automation.lib  import logging
from drizzle.automation.lib  import util
import commands
import datetime
import time

# Errors will look like the following in the log file
# 	func_extra_concat_as_+=error		# Function concatenation with +
# 	func_extra_to_days=error		# Function TO_DAYS
#
# so we look for any line that has "=error" followed by a tab
def check_for_errors_in_output_file(infilename):
  inf= open(infilename, "r+b")

  inlines= inf.readlines()
  error_flag= False
  for inline in inlines:
    position= inline.find('=error\t')
    if position > 0:
        error_flag= True
        logging.info(inline.strip())

  inf.close()
  if error_flag:
    logging.info("crash-me had failing tests.")
    return False
  else:
    return True

def execute(processing_mode, variables):
  # Set/verify some required variables, depending on the server we are benchmarking.

  working_dir= variables['working_dir']
  run_date= datetime.datetime.now().isoformat()
  server_name= variables['server']
  bench_config_name= variables['bench_config_name']

  # need the location where the sqlbench repository is located to run the crash-me command
  crashme_config_variables= util.loadConfigFile("crashme", bench_config_name)
  sqlbench_home= crashme_config_variables['run']['sqlbench_home']

  os.chdir(working_dir)

  # For BZR mode, the "version" of the server (used in identifying the 
  # command run when logging to the database) is the branch and revision number.
  #
  # For MySQL Sandbox mode, the version is the text after the "msb_" prefix
  # on the sandbox.
  if processing_mode == 'bzr':
    server_version= "%s-%s" % (variables['bzr_branch'], variables['bzr_revision'])
  else:
    server_version= variables['mysql_sandbox'].split('_')[1] # Sandbox names are msb_XXXX (e.g. msb_6011 for MySQL 6.0.11)

  # We must instantiate a server and a client adapter which
  # are used to start/stop the server and to query it. Depending
  # on the type of server we are testing/processing, we may also
  # instantiate a "Builder" object, which is used to build the 
  # server from source...
  if server_name in ['drizzled','drizzle']:

    from drizzle.automation.builder.drizzled import DrizzledBzrBuilder as builder_adapter
    from drizzle.automation.client.drizzledb import DrizzleClient as client_adapter

    # Here, depending on the revision, we use a different adapter
    # for the older drizzleadmin-controlled server...
    if str(variables['bzr_revision']) != 'last:1' and int(variables['bzr_revision']) < 950:
      from drizzle.automation.server.olddrizzled import DrizzledServer as server_adapter
    else:
      from drizzle.automation.server.drizzled import DrizzledServer as server_adapter

  elif server_name in ['mysqld','mysql']:
    from drizzle.automation.builder.mysqld import MySQLBzrBuilder as builder_adapter
    from drizzle.automation.client.mysql import MySQLClient as client_adapter
    from drizzle.automation.server.mysqld import MySQLdServer as server_adapter

  else:
    logging.error("Not yet implemented!")
    sys.exit(1)

  server= server_adapter(variables['working_dir'])
  client= client_adapter(variables['working_dir'], server.getPort())

  if variables['no_build'] is False:
    try:
      configure_options= variables['defaults']['configure_options']
    except KeyError:
      configure_options= ""
    try:
      make_options= variables['defaults']['make_options']
    except KeyError:
      make_options= ""

    builder= builder_adapter(variables['working_dir'], configure_options, make_options) 
    builder.build(variables['force_build'])
  
  server.stopAll()

  # clean data directory (var)
  server.clear()

  # Start up the server...
  server.start()

  # change to the sqlbench repository location
  os.chdir(sqlbench_home)

  # output directory to store results using the bzr revision number - example - limits-1225
  output_dirname= "limits-%s" % (variables['bzr_revision'])
  if not os.path.isdir(output_dirname):
    logging.info("Creating %s" % output_dirname)
    os.mkdir(output_dirname)

  output_filename= "%s/%s.cfg" % (output_dirname,server_name)

  # remove the existing configuration file to start fresh
  if os.path.exists(output_filename):
    logging.info("Removing %s" % output_filename)
    os.remove(output_filename)
  
  output_file= open(output_filename,"w")
  # don't support '+' for concatenation
  output_file.writelines("func_extra_concat_as_+=no\n")
  # new boost libraries are causing us to put these limits in, needs investigation
  output_file.writelines("max_text_size=1048576\n")
  output_file.writelines("where_string_size=1048576\n")
  output_file.writelines("select_string_size=1048576\n")
  output_file.flush()
  output_file.close()
  
  crashme_options= "--server=%s --connect-options=port=%d --force --dir=limits-%s --verbose --debug" % (server_name, server.getPort(), variables['bzr_revision'])
  logging.info("Running crash-me %s" % (crashme_options))
  (retcode, output)= commands.getstatusoutput("./crash-me %s " % (crashme_options))
  if retcode != 0:
    logging.error("Failed to run crash-me.  Got error %d:\n%s." % (retcode,output))
    sys.exit(1)
  else:
    if not check_for_errors_in_output_file(output_filename):
      sys.exit(1)
    else: 
      logging.info("crash-me completed succesfully.\n%s." % (output))

  server.stop()

  return True
