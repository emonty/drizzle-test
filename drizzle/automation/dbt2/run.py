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

"""Script to automate running and processing of dbt2 tests."""

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

def log_dbt2_iteration(run_id, connections, test_time, warehouses, stat_file):

  fileHandle= open(stat_file)
  inlines= fileHandle.readlines()

  # set values to a negative number in case we don't find anything in the output file
  tpm='-0'
  rollbacks='-0'
  for inline in inlines:
    fields= inline.split()
    if inline.find("new-order transactions per minute") > 0:
      tpm= fields[0] 
    elif inline.find("rollback transactions") > 0:
      rollbacks= fields[0]

   # insert into database
  sql= ""
  sql= sql + """
  INSERT INTO dbt2_run_iterations (
       run_id
     , tpm
     , connections
     , test_time
     , rollbacks
     , warehouses
     ) VALUES (%d,%0.2f,%d,%d,%d,%d) 
     """ % (
           int(run_id)
         , float(tpm)
         , int(connections)
         , int(test_time)
         , int(rollbacks)
         , int(warehouses)
        )

  from drizzle.automation.lib import db
  db.execute_sql(sql)
  fileHandle.close()

# location where test results are stored, dbt2 expects it to not exist
def remove_directory(output_dirname):
  if os.path.exists(output_dirname):
    logging.info("Removing %s" % output_dirname)
    import shutil
    shutil.rmtree(output_dirname)

def execute(processing_mode, variables):
  # Set/verify some required variables, depending on the server we are benchmarking.

  working_dir= variables['working_dir']
  server_name= variables['server']
  run_date= datetime.datetime.now().isoformat()
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

  # If we are profiling, we must now stop and restart the server
  # under the profiler now that the database is prepared
  util.get_profile_options(server,variables['profiler'])

  run_id= util.getNextRunId()
  config_id= util.getConfigId(bench_config_name)
  
  # load the configuration file
  dbt2_config_variables= util.loadConfigFile("dbt2", bench_config_name)

  # location of dbt2 tools and scripts
  dbt2_home= dbt2_config_variables['run']['dbt2_home']

  bzr_revision= variables['bzr_revision']
  test_time= dbt2_config_variables['run']['dbt2_time']
  warehouses= dbt2_config_variables['run']['dbt2_warehouses']
  warehouses_per_driver= dbt2_config_variables['run']['dbt2_warehouses_per_driver']
  dbname= dbt2_config_variables['run']['dbt2_dbname']

  # load data into database
  if not server.start():
    logging.error("Server failed to start. Can't continue test")
    sys.exit(1)
  cmd= "%s/bin/drizzle/dbt2-drizzle-load-db --path %s --verbose --drizzle_path %s" % (dbt2_home, dbt2_config_variables['run']['dbt2_data_dir'],  os.path.join(working_dir, 'client/drizzle'))
  logging.info("Loading data.... %s " % cmd)
  (retcode, output)= commands.getstatusoutput(cmd)
  if not retcode == 0:
    logging.info("Failed to load data\n%s" % output)
    server.crash_check()
    sys.exit(1)
  server.stop()

  # get list of connections to run with
  connection_levels= [int(x) for x in dbt2_config_variables['run']['dbt2_connections'].split(",")]
  
  # need to set the path so we can find the dbt2 scripts
  temp_env= os.environ["PATH"]
  os.environ["PATH"] = "%s:%s/bin:%s/bin/drizzle" % (temp_env, dbt2_home, dbt2_home)
  logging.info("Setting PATH environment variable to %s" % os.environ["PATH"])

  # run the tests
  # Note that the tests start and stop drizzled after each run
  for connections in connection_levels: 
    output_dirname= "results-%s/%s" % (bzr_revision, connections)
    remove_directory(output_dirname)
    cmd= "%s/bin/dbt2-run-workload -a drizzle -c %d -d %d  -w %d -o %s -i %s -l %d -b %d -D %s" % (dbt2_home, connections, int(test_time), int(warehouses), output_dirname, working_dir, server.getPort(), int(warehouses_per_driver), dbname)
    logging.info("Running %s " % cmd)
    (retcode, output)= commands.getstatusoutput(cmd)
    if not retcode == 0:
      logging.info("Failed to run test with %d connections\n%s" % (connections,output))
      sys.exit(1)

  if variables['no_store_db'] is False:

     util.log_sysbench_run(run_id, config_id, server_name, server_version, run_date)

     # We now log the results of this run - 
     logging.info("Logging dbt2 revision %s results to database for run %d" % (bzr_revision, run_id))
     for connections in connection_levels: 
       stat_file= ("%s/results-%s/%s/report.txt" % (working_dir, bzr_revision, connections))
       log_dbt2_iteration(run_id, connections, test_time, warehouses, stat_file)

  # send email report
  if variables['with_email_report'] is True:
    import drizzle.automation.reports.dbt2 as reports
    email_text= reports.getDbt2Report(working_dir, bench_config_name, run_id, run_date, server_name, variables['bzr_branch'], bzr_revision)
    logging.info("Sending email...")
    # bug https://bugs.launchpad.net/launchpad/+bug/419562 - need to use registered launchpad name for from
    #from_string= ('%s <drizzle-benchmark@lists.launchpad.net>' % socket.gethostname())
    from_string= ('%s <hudson@inaugust.com>' % socket.gethostname())
    util.mail(from_string, variables['dbt2']['report_email'], "DBT2 Report - %s" % server_version, email_text)

  return True
