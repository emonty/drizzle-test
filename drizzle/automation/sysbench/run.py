#! /usr/bin/python
# -*- mode: c; c-basic-offset: 2; indent-tabs-mode: nil; -*-
# vim:expandtab:shiftwidth=2:tabstop=2:smarttab:
#
# Copyright (C) 2009 Sun Microsystems
#
# Authors:
#
#  Jay Pipes <joinfu@sun.com>
#  Monty Taylor <mordred@sun.com>
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
from drizzle.automation.lib import logging
from drizzle.automation.lib import util
import commands
import re
import time
import datetime

# Stores data for a single sysbench iteration in the database
def log_sysbench_iteration(run_id, concurrency, iteration, output):

  logging.info("Logging results to database for concurrency %d, iteration %d" % (concurrency, iteration))

  # Slice up the output report into a matrix and insert into the DB.
  regexes= {
    'tps': re.compile(r".*transactions\:\s+\d+\D*(\d+\.\d+).*")
  , 'deadlocksps': re.compile(r".*deadlocks\:\s+\d+\D*(\d+\.\d+).*")
  , 'rwreqps': re.compile(r".*read\/write\s+requests\:\s+\d+\D*(\d+\.\d+).*")
  , 'min_req_lat_ms': re.compile(r".*min\:\s+(\d*\.\d+)ms.*")
  , 'max_req_lat_ms': re.compile(r".*max\:\s+(\d*\.\d+)ms.*")
  , 'avg_req_lat_ms': re.compile(r".*avg\:\s+(\d*\.\d+)ms.*")
  , '95p_req_lat_ms': re.compile(r".*approx.\s+95\s+percentile\:\s+(\d+\.\d+)ms.*")
  }
  run= {}
  for line in output.split("\n"):
    for key in regexes.keys():
      result= regexes[key].match(line)
      if result:
        run[key]= float(result.group(1)) # group(0) is entire match...

  # Write results to the DB
  sql= """INSERT INTO sysbench_run_iterations (
          run_id
        , concurrency
        , iteration
        , tps
        , read_write_req_per_second
        , deadlocks_per_second
        , min_req_latency_ms
        , max_req_latency_ms
        , avg_req_latency_ms
        , 95p_req_latency_ms
        ) VALUES (%d, %d, %d, %0.2f, %0.2f, %0.2f, %0.2f, %0.2f, %0.2f, %0.2f) 
      """ % (
             int(run_id)
           , int(concurrency)
           , int(iteration)
           , run['tps']
           , run['rwreqps']
           , run['deadlocksps']
           , run['min_req_lat_ms']
           , run['max_req_lat_ms']
           , run['avg_req_lat_ms']
           , run['95p_req_lat_ms']
          )

  from drizzle.automation.lib import db
  
  db.execute_sql(sql)

class Sysbench:

  def __init__(self, bench_config_name, server_name, server_port):
    self._bench_cmd= "sysbench"
    self._bench_config_name= bench_config_name
    self._config_id= None
    self._server_name= server_name
    self._server_port= server_port

  def getConcurrencyLevels(self, sysbench_config_variables, bench_config_name):
    """Returns a sequence of concurrency levels this sysbench will run"""
    try:
      concurrency_levels= [int(x) for x in sysbench_config_variables['run']['concurrency'].split(",")]
      return concurrency_levels
    except KeyError:
      logging.error("concurrency is required in configuration section [run] for %s. Exiting." % bench_config_name)
      sys.exit(1)

  def getIterations(self, sysbench_config_variables, bench_config_name):
    """Returns the number of iterations this sysbench will run"""
    try:
      iterations= int(sysbench_config_variables['run']['iterations'])
      return iterations
    except KeyError:
      logging.error("iterations is required in configuration section [run] for %s. Exiting." % bench_config_name)
      sys.exit(1)

  def getServerOptions(self, sysbench_config_variables, server_name):
    """Returns a dictionary of server-specific options loaded from sysbench config file"""
    if server_name in sysbench_config_variables.keys():
      return sysbench_config_variables[server_name]
    else:
      logging.warning("Did not find any variables in sysbench config file for server section %s" % server_name)
      return {}

  def getConfigureOptions(self):
    """Returns the configure options to use"""
    if len(self._build_options) > 0:
      if 'configure_options' in self._build_options.keys():
        return self._build_options['configure_options']
    return None

  def getMakeOptions(self):
    """Returns the gmake options to use"""
    if len(self._build_options) > 0:
      if 'make_options' in self._build_options.keys():
        return self._build_options['make_options']
    return None

  def setRunOptions(self, run_options):
    """Sets the sysbench run options"""
    self._run_options= run_options
  
  def setBuildOptions(self, build_options):
    """Sets the build options. The build options are in the [build] section of the config file"""
    self._build_options= build_options

  def getRunOptionString(self):
    """Builds the string of options to pass to sysbench during run and prepare"""
    fixed_server_name= self._server_name.replace("drizzled","drizzle").replace("mysqld","mysql")

    # These options are controlled by the automation suite...if they
    # are found in the configuration file, they are ignored...
    ignored_options= [
      'drizzle-host'
    , 'mysql-host'
    , 'drizzle-port'
    , 'mysql-port'
    , 'drizzle-user'
    , 'mysql-user'
    , 'drizzle-db'
    , 'mysql-db'
    , 'db-driver'
    ]

    # These options are controlled by the automation suite...if they
    # are found in the configuration file, the key is checked to ensure
    # it matches the name of the server being tested and the value is used properly
    monitored_options= [
      'drizzle-table-engine'
    , 'mysql-table-engine'
    ]

    # The list of options we return...
    options= [
      "--%s-host=127.0.0.1" % fixed_server_name
    , "--%s-port=%d" % (fixed_server_name, self._server_port)
    , "--%s-user=root" % fixed_server_name
    , "--%s-db=test" % fixed_server_name
    , "--db-driver=%s" % fixed_server_name
    ]
    for key in self._run_options.keys():
      orig_key= key
      # We need to "clean" the options to make them amenable for both server types...
      if key in ignored_options:
        continue
      if key in monitored_options:
        # Key is in form server-xxx-xxx.  Cut off the server part and
        # prepend the server_name needed...
        parts= key.split("-")
        key= "-".join([fixed_server_name] + parts[1:])

      # Ensure option names are output as --option_name
      tmp_key= key
      if not key.startswith("--"):
        tmp_key= "--" + tmp_key
      options.append("%s=%s" % (tmp_key, self._run_options[key]))
      
    return " ".join(options)

  def prepare(self, client):
    """Prepares the sysbench run.  A client instance is passed to prepare()
in order for the Sysbench instance to create its necessary schema."""
    
    """Drop test database if it exists and create a new one"""
    if not util.drop_and_create_test_database(client):
      return False

    logging.info("Preparing sysbench for run.")
    (retcode, output)= commands.getstatusoutput("%s %s prepare" % (self._bench_cmd, self.getRunOptionString()))
    if not retcode == 0:
      logging.error("Failed to prepare sysbench. Ran:\n%s\nGot error:\n%s." % ("%s %s prepare" % (self._bench_cmd, self.getRunOptionString()), output))
      return False

    return True

  def run(self, concurrency):
    """Runs sysbench for the supplied concurrent client connection level.
Returns the text output from sysbench on a successful run."""
    (retcode, output)= commands.getstatusoutput("%s %s --num-threads=%d run" % (self._bench_cmd, self.getRunOptionString(), int(concurrency)))
    if retcode != 0:
      logging.error("Failed to run sysbench at concurrency %s.  Got error:\n%s." % (concurrency, output))
      sys.exit(1)
    else:
      return output

def execute(processing_mode, variables):
  # Set/verify some required variables, depending on the server
  # we are benchmarking.

  working_dir= variables['working_dir']
  bench_config_name= variables['bench_config_name']
  run_date= datetime.datetime.now().isoformat()

  server_name= variables['server']

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

  # Initialize sysbench runner instance and load config file
  sysbench= Sysbench(bench_config_name, server_name, server.getPort())

  sysbench_config_variables= util.loadConfigFile("sysbench", bench_config_name)
  sysbench.setRunOptions(sysbench_config_variables['sysbench'])

  if 'build' in sysbench_config_variables.keys():
    sysbench.setBuildOptions(sysbench_config_variables['build'])

  # The sysbench configuration file can specify configure and make options
  # which is why we delay building until this point, which is after the 
  # sysbench configuration file is loaded.

  make_options= sysbench.getMakeOptions() or variables['defaults']['make_options']
  configure_options= sysbench.getConfigureOptions() or variables['defaults']['configure_options']

  if variables['no_build'] is False:
    builder= builder_adapter(variables['working_dir'], configure_options, make_options)
    builder.build(variables['force_build'])
  
  # Set the startup options of the server from the sysbench configuration file
  server.setStartOptions(sysbench.getServerOptions(sysbench_config_variables, server_name))

  server.stopAll()

  # Clear out the data dir from any prior runs...
  if server.ping():
    server.stop()

  server.clear()

  # Start up the server...
  server.start()

  if not sysbench.prepare(client):
    server.stop()
    sys.exit(1)

  # If we are profiling, we must now stop and restart the server
  # under the profiler now that the database is prepared
  util.get_profile_options(server,variables['profiler'])

  concurrency_levels= sysbench.getConcurrencyLevels(sysbench_config_variables, bench_config_name)
  iterations= sysbench.getIterations(sysbench_config_variables, bench_config_name)
  if variables['no_store_db'] is False:
    run_id= util.getNextRunId()
    config_id= util.getConfigId(bench_config_name)

  # Run the benchmarks for the specified config
  for concurrency in concurrency_levels:
    for iteration in range(iterations):

      if not server.ping(quiet= True):
        logging.warning("Server not running. Re-starting...")
        server.start()

      logging.info("Running sysbench config %s for concurrency at %d - iteration %d." % (bench_config_name, concurrency, iteration))

      result= sysbench.run(concurrency)

      if variables['no_store_db'] is False:

        # Only on the first successful iteration and first concurrency create
        # the new run record in the database
        if concurrency == concurrency_levels[0] and iteration == 0:
          util.log_sysbench_run(run_id, config_id, server_name, server_version, run_date)

        # We now log the results of this particular iteration
        log_sysbench_iteration(run_id, concurrency, iteration, result)

    # If we store status counters, do so now...
    if variables['with_show_status'] is True and variables['no_store_db'] is False:
      util.log_show_status(client, run_id, concurrency)

    server.stop()

    time.sleep(3)

    # Clear, start server and prepare bench if not the very last run...
    if concurrency != max(concurrency_levels):

      # Clear data files and restart the server after each concurrency run.
      server.clear()
      # Restart server and re-prepare sysbench
      server.start()
      sysbench.prepare(client)

  if variables['with_email_report'] is True:
    import drizzle.automation.reports.sysbench as reports
    email_text= reports.getSysbenchRegressionReport(working_dir, bench_config_name, run_id, run_date, server_name, variables['bzr_branch'], int(variables['bzr_revision']))
    # bug https://bugs.launchpad.net/launchpad/+bug/419562 - need to use registered launchpad name for from
    #from_string= ('%s <drizzle-benchmark@lists.launchpad.net>' % socket.gethostname())
    from_string= ('%s <hudson@inaugust.com>' % socket.gethostname())
    util.mail(from_string, variables['sysbench']['report_email'], "SYSBENCH Regression Report - %s" % server_version, email_text)

  return True
