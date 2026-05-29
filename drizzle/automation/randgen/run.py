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

"""Script to automate running random query generator."""

import sys
import os
import os.path
from drizzle.automation.lib  import logging
from drizzle.automation.lib  import util
import commands
import datetime
import time

def execute(processing_mode, variables):
  # Set/verify some required variables, depending on the server
  # we are processing

  working_dir= variables['working_dir']
  run_date= datetime.datetime.now().isoformat()
  server_name= variables['server']
  bench_config_name= variables['bench_config_name']

 
  # need the location where the randgen repository is located to run the randgen commands
  randgen_config_variables= util.loadConfigFile("randgen", bench_config_name)
  randgen_home= randgen_config_variables['run']['randgen_home']
  threads= randgen_config_variables['run']['threads']
  queries= randgen_config_variables['run']['queries']
  engine= randgen_config_variables['run']['engine']
  debug_flag= int(randgen_config_variables['run']['debug'])

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
    configure_options= configure_options + " --prefix=%s" %(variables['working_dir'])

    try:
      make_options= variables['defaults']['make_options']
    except KeyError:
      make_options= ""

    builder= builder_adapter(variables['working_dir'], configure_options, make_options) 
    builder.build(variables['force_build'])
  
  # Set the startup options of the server from the sysbench configuration file
  server.setStartOptions(util.getServerOptions(randgen_config_variables, server_name))

  # stop any servers that are running
  server.stopAll()

  # clean data directory (var)
  server.clear()

  # determine if we require a validation server or not
  # if we do, we start another with a separate vardir
  # from the basedir under test
  if variables['with_validation_server'] is True:
    from drizzle.automation.server.drizzled import DrizzledServer as validator_adapter
    from drizzle.automation.client.drizzledb import DrizzleClient as validator_client_adapter
    validator_options = {}
    validator_options["port"] = 9307
    validator_options["datadir"] = 'var1'
    validation_server = validator_adapter(variables['working_dir'],validator_options)
    validator_client= validator_client_adapter(variables['working_dir'], validation_server.getPort())
    logging.info("Test requires validation server...")
    validation_server.clear()
    validation_server.start()
    time.sleep(20)
    if not util.drop_and_create_test_database(validator_client):
      validation_server.stop()
      sys.exit(1)

  # get the list of tests that are specified
  # in the configuration file in the randgen_test section
  list_of_tests= randgen_config_variables['randgen_tests']

  server.start()
  time.sleep(20)
  # Drop test database if it exists and create a new one
  if not util.drop_and_create_test_database(client,variables['with_validation_server']):
    server.stop()
    sys.exit(1)

  # If we are profiling, we must now stop and restart the server
  # under the profiler now that the database is prepared
  util.get_profile_options(server,variables['profiler'])

  # change to the randgen repository to run the tests
  os.chdir(randgen_home)

  # loop through the list of tests and run each one
  # start and stop the server each time so we have a clean start each run
  fail_tests= 0
  pass_tests= 0
  for key in list_of_tests.keys():
    # run the test
    cmd= "./gentest.pl --dsn=dbi:drizzle:host=localhost:port=%s:user=root:password="":database=test --threads=%s --queries=%s --engine=%s %s" % (server.getPort(),threads,queries,engine,list_of_tests[key])
    logging.info("Running : %s with %s" % (key, cmd))
    (retcode, output)= commands.getstatusoutput(cmd)
    if not retcode == 0:
      logging.info("%s FAILED\n%s" % (key, output))
      fail_tests= fail_tests + 1
    else:
      # We check if the server is still running as the randgen currently
      # doesn't report if the server has gone away very well for Drizzle
      # We can see about removing this check + code once
      # the randgen plays better with Drizzle
      if not server.ping(quiet= True):
        logging.info("%s FAILED\n%s" % (key, output))
        fail_tests = fail_tests + 1
        server.crash_check()
      else: # end of the check for a still-running server
        logging.info("%s Passed" % key)
        pass_tests= pass_tests + 1
        if debug_flag != 0:
          logging.info("%s OUTPUT = \n%s" % (key, output))

    # we stop / clear / restart the server at the end of the test
    if server.ping(): # don't bother trying to stop the server if it isn't running
      server.stop()
      time.sleep(3)
    server.clear()
    server.start()
    if not util.drop_and_create_test_database(client,variables['with_validation_server']):
      server.stop()
      sys.exit(1)     
    if variables['with_validation_server'] is True:
      if validation_server.ping():
        validation_server.stop()
        time.sleep(3)
      validation_server.clear()
      validation_server.start()
      if not util.drop_and_create_test_database(validator_client):
        validation_server.stop()
        sys.exit(1) 

  server.stop()
  if variables['with_validation_server'] is True:
    validation_server.stop()

  # output final results, return non-zero status if any test failures
  logging.info("%d tests passed" % pass_tests)
  logging.info("%d tests failed" % fail_tests)
  if fail_tests > 0:
    sys.exit(1)
    
  return True
