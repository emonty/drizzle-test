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

"""Just some useful functions"""

import sys
import textwrap
import os
import types
from drizzle.automation.lib import logging
from drizzle.automation.lib import db

def pretty_print_configuration(configuration, key=None, indent_level= 0):
  """Prints configuration variables for the run."""
  if key:
    print "%s%s: " % ("  "*indent_level, key)
  if type(configuration) is types.DictType:
    for conf_key in configuration.keys():
      pretty_print_configuration(configuration[conf_key], conf_key, indent_level+1)
  else:
    print textwrap.fill("%s%s" % ("  "*(indent_level+1), configuration))

def mail(sender='', to='', subject='', text=''):
  """
  Usage:
  mail('somemailserver.com', 'me@example.com', 'someone@example.com', 'test', 'This is a test')
  """
  headers = "From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n" % (sender, to, subject)
  message = headers + text
  import smtplib
  mailServer = smtplib.SMTP('localhost')
  mailServer.sendmail(sender, to, message)
  mailServer.quit()

def drop_and_create_test_database(client, truncate_transaction_log=False):
  """Prepares the benchmark run.  A client instance is passed to prepare()
in order for the instance to create its necessary schema."""

  logging.info("Dropping any test database previously setup.")
  if not client.execute("DROP DATABASE IF EXISTS test"):
    return False

  logging.info("Creating test database.")
  if not client.execute("CREATE DATABASE test"):
    return False

  if truncate_transaction_log:
  # We want to clear the log after we create the 'test' db
  # Can be problematic otherwise
    if not client.execute("SET GLOBAL transaction_log_truncate_debug= true"):
      return False
    
  return True

def log_sysbench_run(run_id, config_id, server_name, server_version, run_date):
  """Creates a new run record in the database for this run"""
  sql= """INSERT INTO bench_runs (
          run_id
        , config_id
        , server
        , version
        , run_date
        ) VALUES (%d, %d, '%s', '%s', '%s')
      """ % (
        run_id
      , config_id
      , server_name
      , server_version
      , run_date)
  from drizzle.automation.lib import db
  
  db.execute_sql(sql)

def getConfigId(bench_config_name):
  """Returns the integer ID of the configuration name used in this run."""

  # If we have not already done so, we query the local DB for the ID
  # matching this sqlbench config name.  If none is there, we insert
  # a new record in the bench_config table and return the newly generated
  # identifier.

  sql= "SELECT config_id FROM bench_config WHERE name = '%s'" % bench_config_name

  from drizzle.automation.lib import db
  result= db.get_select(sql)
    
  if len(result) == 0:
    # Insert a new record for this config and return the new ID...
    sql= "INSERT INTO bench_config (config_id, name) VALUES (NULL, '%s')" % bench_config_name
    db.execute_sql(sql)
    return getConfigId(bench_config_name)
  else:
    config_id= int(result[0][0])

  return config_id

def getNextRunId():
  """Returns a new run identifier from the database.  
     The run ID is used in logging the results of the run iterations."""
  sql= "SELECT MAX(run_id) as new_run_id FROM bench_runs"

  from drizzle.automation.lib import db
  result= db.get_select(sql)
  if result[0][0] >= 1:
    new_run_id= int(result[0][0]) + 1
  else:
    new_run_id= 1

  return new_run_id

# Find the specific last run_id which corresponds to the revision and branch ...
def getLastRunId(bench_config_name, server_name, bzr_branch, bzr_revision):

  version= bzr_branch + '-' + str(bzr_revision)

  sql= """
SELECT 
  run_id
FROM bench_config c
NATURAL JOIN bench_runs r
WHERE c.name = '%s'
AND r.server = '%s'
AND r.version LIKE '%s%%'
ORDER BY run_id DESC
LIMIT 1
""" % (
        bench_config_name
      , server_name
      , version
      )
  results= db.get_select(sql)

  if len(results) == 1:
    return int(results[0][0])
  else:
    return False

  return True

# if we are profiling, we must stop and restart the server
# under the profiler now that the database is prepared
def get_profile_options(server, profile_option):

  if profile_option is not None:
    server.stop()
    profiler_name= profile_option
    profiler_log_file= profiler_name + '.out'
    if profiler_name == 'memcheck':
      from drizzle.automation.profiler.memcheck import MemcheckProfiler as profiler_adapter
    elif profiler_name == 'callgrind':
      from drizzle.automation.profiler.callgrind import CallgrindProfiler as profiler_adapter
    elif profiler_name == 'cachegrind':
      from drizzle.automation.profiler.cachegrind import CachegrindProfiler as profiler_adapter
    profiler= profiler_adapter(profiler_log_file)
    server.setProfiler(profiler)
    server.start()

# Finds and parses the configuration file for the supplied config name
# A configuration file containing benchmark program and server
# parameters is required.  If the --bench-config=NAME is a relative
# filename, we search in /etc/drizzle-automation/sysbench/ for a
# file called NAME.cnf
def loadConfigFile(benchmark_name, bench_config_name):

  logging.info("Loading configuration for config name %s." % bench_config_name)
  bench_config_variables= {}

  locations=[]
  bench_config_file= bench_config_name
  if not bench_config_file.endswith(".cnf"):
    bench_config_file= bench_config_file + ".cnf"

  if not bench_config_file.startswith(os.path.sep):
    # Assume all relative config files are in /etc/drizzle-automation/sysbench/
    locations.append(os.path.join(os.path.sep, "etc", "drizzle-automation", benchmark_name, bench_config_file))
    locations.append(os.path.expanduser(os.path.join("~", ".drizzle-automation", benchmark_name, bench_config_file)))
  else:
    locations.append(bench_config_file)

  bench_config_file_found=False
  for test_bench_config_file in locations:
    if os.path.exists(test_bench_config_file):
      bench_config_file_found=True
  if not bench_config_file_found:
    logging.error("Specified configuration file not found: \"%s\". Exiting." % bench_config_file)
    sys.exit(1)

  import ConfigParser
  parser= ConfigParser.RawConfigParser()
  parser.read(locations)
  for sec in parser.sections():
    bench_config_variables[sec]= {}
    for k,v in parser.items(sec):
      bench_config_variables[sec][k]= v

  return bench_config_variables

def log_show_status(client, run_id, concurrency):
  from drizzle.automation.lib import db

  logging.info("Logging status variables to database for concurrency %d" % (concurrency))

  results= client.fetchAllAssoc("SHOW GLOBAL STATUS")
  for result in results:
    # Strip out non-integer status counters...
    try:
      value= int(result['Value'])
    except:
      continue
    name= result['Variable_name']
    # Write results to the DB
    sql= """INSERT INTO bench_show_status_history (
          run_id
        , concurrency
        , variable_name
        , value
        ) VALUES (%d, %d, '%s', %d)""" % (int(run_id), int(concurrency), name, int(value))
    db.execute_sql(sql)

# Returns a dictionary of server-specific options loaded from the benchmark config file
def  getServerOptions(config_variables, server_name):
  if server_name in config_variables.keys():
    return config_variables[server_name]
  else:
    return {}

