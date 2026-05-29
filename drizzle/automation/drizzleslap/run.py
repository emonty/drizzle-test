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

"""Script to automate running and processing of drizzleslap tests."""

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

# Stores data for a drizzleslap iteration in the database
# input file is a cvs file that looks like the following:
# innodb,write,0.03,0,0.05,0.05,0.04,2,1,1,47
# innodb,write,0.05,0.04,0.05,0.09,0,2,25,25,1
# innodb,write,0.4,0.4,0.41,0.81,0.01,2,50,50,0
# innodb,write-scale,0.37,0.37,0.38,0.75,0.01,2,25,25,22
# innodb,write-scale,0,0,0,0,0,2,1,1,22
# innodb,write-scale,0.72,0.7,0.73,1.44,0.02,2,50,50,22
# .......
#
def log_drizzleslap_iteration(run_id, bzr_revision, csv_file):

  logging.info("Logging drizzleslap revision %s results to database for run %d" % (bzr_revision, run_id))

  fileHandle= open(csv_file)
  inlines= fileHandle.readlines()
  found_block= False

  for inline in inlines:
      fields= inline.split(",")
      # insert into database
      sql= ""
      sql= sql + """
      INSERT INTO drizzleslap_run_iterations (
          run_id
        , engine_name
        , test_name
        , queries_avg
        , queries_min
        , queries_max
        , total_time
        , stddev
        , iterations
        , concurrency
        , concurrency2
        , queries_per_client
        ) VALUES (%d,'%s','%s','%s',%0.3f,%0.3f,%0.3f,%0.3f,%0.3f,%d,%d,%d) 
        """ % (
              int(run_id)
            , fields[0]
            , fields[1]
            , float(fields[2])
            , float(fields[3])
            , float(fields[4])
            , float(fields[5])
            , float(fields[6])
            , int(fields[7])
            , int(fields[8])
            , int(fields[9]) 
            , int(fields[10])
           )

      from drizzle.automation.lib import db
      db.execute_sql(sql)

  fileHandle.close()

def execute(processing_mode, variables):
  # Set/verify some required variables, depending on the server we are benchmarking.

  working_dir= variables['working_dir']
  server_name= variables['server']
  run_date= datetime.datetime.now().isoformat()
  bench_config_name= variables['bench_config_name']

  drizzleslap_config_variables= util.loadConfigFile("drizzleslap", bench_config_name)

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

  # Set the startup options of the server
  server.setStartOptions(util.getServerOptions(drizzleslap_config_variables, server_name))

  # stop any servers that are running  
  server.stopAll()

  # clean data directory (var)
  server.clear()

  # Start up the server...
  if not server.start():
    logging.error("Server failed to start. Can't continue test")
    sys.exit(1)

  # create test database
  if not util.drop_and_create_test_database(client):
    if not server.crash_check():
      server.stop()
    sys.exit(1)

  if variables['no_store_db'] is False:
    run_id= util.getNextRunId()
    config_id= util.getConfigId(bench_config_name)

  # load the configuration file
  drizzleslap_config_variables= util.loadConfigFile("drizzleslap", bench_config_name)

  # get the list of tests that are specified
  # in the configuration file in the drizzleslap_tests section
  list_of_tests= drizzleslap_config_variables['drizzleslap_tests']

  # csv file name includes the bzr version number /tmp/drizzleslap-1172.csv
  csv_file= ("/tmp/drizzleslap-%s.csv" % (variables['bzr_revision']))
  common_options= drizzleslap_config_variables['run']['common_options']
  concurrency_levels= [int(x) for x in drizzleslap_config_variables['run']['concurrency'].split(",")]
  iterations= drizzleslap_config_variables['run']['iterations']

  # remove csv file to start fresh
  if os.path.exists(csv_file):
    os.remove(csv_file)

  # loop through the list of tests and run each one
  # start and stop the server each time so we have a clean start each run
  fail_tests= 0
  pass_tests= 0
  for concurrency in concurrency_levels:
    for key in list_of_tests.keys():
      # run the test
      cmd= "%s/client/drizzleslap --port=%s --label=%s --concurrency=%s --iterations=%s --csv=%s %s %s" % (working_dir, server.getPort(), key, concurrency, iterations, csv_file, common_options, list_of_tests[key])
      logging.info("Running test: %s with %s" % (key, cmd))
      (retcode, output)= commands.getstatusoutput(cmd)
      if not retcode == 0:
        logging.info("%s Failed with %d\n%s" % (key, retcode, output))
        fail_tests= fail_tests + 1
      else:
        logging.info("%s Passed" % key)
        pass_tests= pass_tests + 1
      # we stop, clear and restart the server for the next test
      if not server.crash_check():
        server.stop()
      time.sleep(3)
      server.clear()
      server.start()
      if not util.drop_and_create_test_database(client):
        if not server_crash_check():
          server.stop()
        sys.exit(1)  

      time.sleep(2)

  # output final results, return non-zero status if any test failures
  logging.info("%d tests passed" % pass_tests)
  logging.info("%d tests failed" % fail_tests)
  if fail_tests > 0:
    sys.exit(1)

  server.stop()

  if variables['no_store_db'] is False:

     util.log_sysbench_run(run_id, config_id, server_name, server_version, run_date)

     # We now log the results of this run - 
     log_drizzleslap_iteration(run_id, variables['bzr_revision'], csv_file)

  # send email report
  if variables['with_email_report'] is True:
    import drizzle.automation.reports.drizzleslap as reports
    email_text= reports.getDrizzleslapReport(working_dir, bench_config_name, run_id, run_date, server_name, variables['bzr_branch'], int(variables['bzr_revision']))
    logging.info("Sending email...")
    # bug https://bugs.launchpad.net/launchpad/+bug/419562 - need to use registered launchpad name for from
    #from_string= ('%s <drizzle-benchmark@lists.launchpad.net>' % socket.gethostname())
    from_string= ('%s <hudson@inaugust.com>' % socket.gethostname())
    util.mail(from_string, variables['drizzleslap']['report_email'], "Drizzleslap Report - %s" % server_version, email_text)

  return True
