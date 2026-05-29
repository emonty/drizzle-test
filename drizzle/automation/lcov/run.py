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

"""Script to automate running and processing of GCOV/LCOV data."""

import sys
import os
import re
import os.path
from drizzle.automation.lib  import logging
import commands
import datetime

# in the lcov/index.html file look for the total percentage of the
# top level directories (drizzled, client), except plugin which is processed differently
def find_coverage_percentage(dir, file_name):
  fileHandle= open(file_name).read()
  pattern= "href=\"%s/index.html\"" % dir
  pos= fileHandle.find(pattern)

  if pos > 0:
    float_pattern= "alt=\""
    new_pos= fileHandle.find(float_pattern, pos)
    if new_pos:
      new_pos= new_pos + 5 # length of alt="
      end_pos= new_pos + 1
      while fileHandle[end_pos].isdigit() or fileHandle[end_pos] == '.':
        end_pos= end_pos + 1
      percentage= float(fileHandle[new_pos:end_pos])
  else:
    percentage= 0.0
 
  #fileHandle.close()
  return percentage

# Because plugin does not have files in its root directory
# we need to find all the index.html files in the plugin
# directory and get the percent coverage for each and 
# add to a grand total divided by total count of plugin index.html files
def find_coverage_percentage_for_plugin_dir(file_name):
  fileHandle= open(file_name)
  pattern= re.compile('href="plugin/\w+/*\w*/index.html"')
  float_pattern= re.compile('alt="')

  inlines= fileHandle.readlines()
  found= 0
  counter=0
  total=0
  for inline in inlines:
    # first find a line to matches pattern, which will be something like:
    #       href="plugin/ascii/index.html
    if not found:
      first_pos= pattern.search(inline)
      if (first_pos):
        found= 1
     # once we have found pattern, now get the next line that has float_pattern
     # and look for the percent coverage number for this plugin directory
     # it is found right after the float_pattern
    if found:
      next_pattern= float_pattern.search(inline)
      if (next_pattern):
        begin_position = next_pattern.end()
        end_position = begin_position + 1
        while inline[end_position].isdigit() or inline[end_position] == '.':
          end_position= end_position + 1
        dir_percent= float(inline[begin_position:end_position])
        total= total + dir_percent
        counter = counter + 1
        found= 0

  fileHandle.close()
  return total/counter

# print out failing tests if we encounter test failures
def check_test_suite_logs():
  infilename= "tests/var/log/drizzle-test-run.log"
  inf= open(infilename, "r+b")

  inlines= inf.readlines()
  in_ignore_block= False
  for inline in inlines:
    if inline.startswith("[ fail ]"):
      # print the line before as that should be the test name
      logging.error("Test failed: %s" % previous_line);
      in_ignore_block= True
    if inline.startswith("Stopping All Servers") and in_ignore_block == True:
      in_ignore_block= False
      continue
    if in_ignore_block == True:
      logging.error(inline.strip())
    # keep track of the current line as we will need this when we find a failure 
    previous_line= inline.strip()
  inf.close()

def execute(processing_mode, variables):
  # Set/verify some required variables, depending on the server
  # we are processing

  working_dir= variables['working_dir']
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

  # Reset all coverage counters
  logging.info("Resetting all LCOV coverage counters.")

  cmd= "lcov --directory %s --zerocounters" % (working_dir)
  (retcode, output)= commands.getstatusoutput(cmd)
  if not retcode == 0:
    logging.error("Failed to zero-out coverage counters for %s. Exiting." % (working_dir))
    sys.exit(1)

  # Depending on the type of server we are testing/processing, we may
  # instantiate a "Builder" object, which is used to build the 
  # server from source...
  if server_name == 'drizzled':

    if variables['no_build'] is False:
      from drizzle.automation.builder import drizzled as builder_adapter
      if "make_options" in variables['defaults'].keys():
        make_options= variables['defaults']['make_options']
      else:
        make_options= "-j2"
      configure_options= '--with-debug --enable-coverage --enable-profiling'
      builder= builder_adapter.DrizzledBzrBuilder(variables['working_dir'], configure_options, make_options)
      builder.build()

  elif server_name == 'mysqld':

    pass # Not currently building mysql from source...

  else:
    logging.error("Not yet implemented!")
    sys.exit(1)

  # Run the test suite
  logging.info("Running test suite.")

  (retcode, ignored)= commands.getstatusoutput("make lcov")

  if retcode != 0:
    logging.error("Test suite failed to pass all tests. Exiting.")
    check_test_suite_logs()
    sys.exit(1)

  if variables['no_rsync'] is False:

    # rsync the reports to drizzle.org
    logging.info("Syncing LCOV results with docs.drizzle.org.")

    (retcode, output)= commands.getstatusoutput("rsync -avz lcov_html/ %s@docs.drizzle.org:web/lcov/" % variables['ssh']['ssh_user'])

    if not retcode == 0:
      logging.error("Failed to rsync the reports to docs.drizzle.org. Got error: %s" % output)
      sys.exit(1)

  # Scrape the top-level percentages from lcov/index.html and store them in DB
  if variables['no_store_db'] == False:
    logging.info("Storing results of this run in local DB.")

    # Scrape the percentages...
    percentages= {}

    # html reports end up here post 'make lcov'
    output_dir="lcov_html"

    # Set of directories we're interested in running coverage reports on
    lcov_dirs= variables['lcov']['directories'].split(',')

    # Grab our index file for the lcov reports
    for dir in lcov_dirs:

      file_name= "%s/%s/index.html" % (working_dir, output_dir)
       # in the lcov/index.html file look for the total percentage of the
       # top level directories (drizzled, client), except plugin which is processed differently
       # since there are multiple entries in the file for plugin percentages
      if dir == 'plugin':
        percentages[dir]= find_coverage_percentage_for_plugin_dir(file_name)
      else:
        percentages[dir]= find_coverage_percentage(dir, file_name)

    # Insert into the DB...
    for dir in lcov_dirs:
      sql= ""
      logging.info("%s %s %s %s %0.2f " % (server_name, server_version, dir, run_date, percentages[dir]))
      sql= sql + """
      INSERT INTO lcov_stats (server, version, dir_name, run_date, coverage_percent) VALUES ('%s','%s','%s','%s', %0.2f); """ % (server_name, server_version, dir, run_date, percentages[dir])

      from drizzle.automation.lib import db
      db.execute_sql(sql)

  return True


