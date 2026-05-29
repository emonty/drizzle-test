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
from drizzle.automation.lib import util
import commands
import re
import time
import datetime

# Stores data for a sqlbench iteration in the database
# input file has a section that looks like the following:
# Operation             seconds     usr     sys     cpu   tests
# alter_table_add                       13.00    0.01    0.00    0.01     100
# alter_table_drop                      12.00    0.00    0.00    0.00      91
# connect                                2.00    0.84    0.36    1.20    2000
# .......
# We want to start grabbing lines at the alter_table_add line until the end of the file
#
def log_sqlbench_iteration(run_id, infile_name, storage_engine):

  fileHandle= open(infile_name)
  inlines= fileHandle.readlines()
  found_block= False

  for inline in inlines:
    # look for first line that starts with alter_table_add
    if inline.startswith("alter_table_add"):
      found_block= True
    if found_block == False:
      continue
    else:
      # parse line
      fields= inline.split()
      # insert into database
      sql= ""
      sql= sql + """
      INSERT INTO sqlbench_run_iterations (run_id, operation_name, seconds, usr, sys, cpu, tests, engine) VALUES (%d,'%s', %0.2f, %0.2f, %0.2f, %0.2f, %d, '%s'); """ % (run_id, fields[0], float(fields[1]), float(fields[2]), float(fields[3]), float(fields[4]), int(fields[5]), storage_engine)

      from drizzle.automation.lib import db
      db.execute_sql(sql)

  fileHandle.close()

def check_for_errors_in_output_file(infile_name):
  inf= open(infile_name, "r+b")

  inlines= inf.readlines()
  error_flag= False
  for inline in inlines:
    position= inline.find('Failed')
    if position > 0:
        error_flag= True
        logging.info(inline.strip())

  inf.close()
  if error_flag:
    logging.info("sqlbench had failing tests.")
    return True
  else:
    return False


def run_sqlbench(sqlbench_script, sqlbench_options):
  """Runs sqlbench for the supplied client Returns the text output on a successful run."""
  (retcode, output)= commands.getstatusoutput("%s %s " % (sqlbench_script, sqlbench_options))
  if retcode != 0:
    logging.error("Failed to run sqlbench.  Got error:\n%s." % (output))
    sys.exit(1)
  else:
    return output

def execute(processing_mode, variables):
  # Set/verify some required variables, depending on the server we are benchmarking.

  working_dir= variables['working_dir']
  run_date= datetime.datetime.now().isoformat()
  server_name= variables['server']
  # name of the configuration file to use
  bench_config_name= variables['bench_config_name']
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

  # create test database
  if not util.drop_and_create_test_database(client):
    server.stop()
    sys.exit(1)

  run_id= util.getNextRunId()
  config_id= util.getConfigId(bench_config_name)

  # load the configuration file
  sqlbench_config_variables= util.loadConfigFile("sqlbench", bench_config_name)

  # need the location where the sqlbench repository is located
  sqlbench_home= sqlbench_config_variables['run']['sqlbench_home']

  debug_flag= int(sqlbench_config_variables['run']['debug'])

  try:
    storage_engine= variables['engine']
  except KeyError:
    storage_engine= 'innodb'

  # file name is in the sqlbench_home/results-<bzr_revision> directory
  # file name is "RUN-server_name-bzr_revision-hostname"
  # example - results-1125/RUN-drizzled-1125-orisndriz05
  # include engine name if --engine is specified
  dir_name= ("results-%s-%s" % (storage_engine, variables['bzr_revision']))
  infile_name= ("%s/RUN-%s-%s-%s" % (dir_name, server_name, variables['bzr_revision'], socket.gethostname()))

  os.chdir(sqlbench_home)
  sqlbench_script= "./run-all-tests"
  
  sqlbench_options= ""
  if debug_flag > 0:
      sqlbench_options= sqlbench_options + "--debug --verbose "

  sqlbench_options= sqlbench_options + "--server=%s --dir=%s --log --connect-options=port=%d --bzr-repo=%s --machine=%s --create-options=ENGINE=%s" % (server_name, dir_name, server.getPort(), working_dir, socket.gethostname(), storage_engine)
  
  logging.info("Running sqlbench %s" % (sqlbench_options))

  result= run_sqlbench(sqlbench_script, sqlbench_options)
  # Need to also look within the infilename to see if anything has failed
  # sqlbench doesn't stop if one of the tests fails, it keeps going
  if check_for_errors_in_output_file(infile_name) is True:
    sys.exit(1)
	

  if variables['no_store_db'] is False:

     util.log_sysbench_run(run_id, config_id, server_name, server_version, run_date)

     # We now log the results of this run - 
     logging.info("Logging %s revision %s results to database for run %d" % (server_name, variables['bzr_revision'], run_id))
     log_sqlbench_iteration(run_id, infile_name,storage_engine)

  server.stop()

  time.sleep(3)

  # send email report
  if variables['with_email_report'] is True:
    import drizzle.automation.reports.sqlbench as reports
    email_text= reports.getSqlbenchReport(working_dir, bench_config_name, run_id, run_date, server_name, variables['bzr_branch'], int(variables['bzr_revision']), storage_engine)
    logging.info("Sending email...")
    # bug https://bugs.launchpad.net/launchpad/+bug/419562 - need to use registered launchpad name for from
    #from_string= ('%s <drizzle-benchmark@lists.launchpad.net>' % socket.gethostname())
    from_string= ('%s <hudson@inaugust.com>' % socket.gethostname())
    util.mail(from_string, variables['sysbench']['report_email'], "SQLBENCH Regression Report - %s" % server_version, email_text)

  return True
