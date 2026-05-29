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

"""Processes command line options for automation scripts"""

import sys
import os
import exceptions
import optparse
from drizzle.automation.lib  import logging

# The valid commands for the automation runner
valid_commands= [
  'crashme'
, 'dbt2'
, 'doxy'
, 'drizzleslap'
, 'lcov'
, 'randgen'
, 'sloc'
, 'sqlbench'
, 'sysbench'
, 'valgrind'
, 'report'
]

# Printed for help
usage= """%prog [options] COMMAND

Where COMMAND is one of:

crashme             Run crash-me limits test
dbt2                Run benchmarks using dbt2
doxy                Process Doxygen source code documentation
drizzleslap	    Run drizzleslap tests
lcov                Process LCOV code coverage
randgen		    Run Random Query Generator
sloc                Process SLOC coverage
sqlbench            Run benchmarks using sqlbench
sysbench            Run benchmarks using sysbench
valgrind            Process Valgrind tests
report              Run report against existing data"""

# Create the CLI option parser
parser= optparse.OptionParser(usage=usage)

# Add non-grouped options...
parser.add_option(
    "--bench-config-name"
  , help="DBT2/DRIZZLESLAP/SYSBENCH/SQLBENCH command only. Sets the bench configuration to use."
  )
parser.add_option(
    "--dry-run"
  , action="store_true"
  , default= False
  , help="Check and validate the command and sandbox, but do not run the process. [default: %default]"
  )
parser.add_option(
    "-e"
  , "--engine"
  , metavar="ENGINE"
  , default="innodb"
  , help="SQLBENCH only command. Specify storage engine to be used."
  )
parser.add_option(
    "-f"
  , "--force"
  , action="store_true"
  , default= False
  , help="Don't let failures (e.g. in make test) stop the process. [default: %default]"
  )
parser.add_option(
    "--force-build"
  , action="store_true"
  , default= False
  , help="Rebuild the server even if there is a server binary already built. This is useful if you change configure or make options."
  )
parser.add_option(
    "--ld-preload"
  , metavar="LOCATION"
  , help="Specify location of a shared library to pre-load"
  )
parser.add_option(
  "--log-file"
  , default= "stdout"
  , help="The location of a file to use in logging the run.       [default: %default]"
  )
parser.add_option(
    "--no-build"
  , action="store_true"
  , default= False
  , help="Don't (re)build the server if the command requires building a server. [default: %default]"
  )
parser.add_option(
    "--no-pull"
  , action="store_true"
  , default= False
  , help="Don't pull source code from launchpad bzr repository [default: %default]"
  )
parser.add_option(
    "--no-rsync"
  , action="store_true"
  , default= False
  , help="Don't rsync the results anywhere.               [default: %default]"
  )
parser.add_option(
    "--no-store-db"
  , action="store_true"
  , default= False
  , help="Don't store the results in a database.          [default: %default]"
  )
parser.add_option(
    "--profiler"
  , metavar="PROFILER_NAME"
  , choices=['memcheck','callgrind','cachegrind',None]
  , default=None
  , help="The name of the profiler you want to run against the server."
)
parser.add_option(
    "--server"
  , choices=['drizzled','mysqld']
  , default='drizzled'
  , help="The type of server being tested/processed.      [default: %default]"
  )
parser.add_option(
    "--use-root-sandbox"
  , action="store_true"
  , default= False
  , help="Use the value of bzr_repo_dir for builds.          [default: %default]"
  )
parser.add_option(
    "--with-email-report"
  , action="store_true"
  , default= False
  , help="DBT2/DRIZZLESLAP/SQLBENCH/SYSBENCH REPORT command.  Sends a text report to those recipients in [dbt2][sqlbench][sysbench][drizzleslap][report_email] configuration variable."
  )
parser.add_option(
    "--with-show-status"
  , action="store_true"
  , default= False
  , help="DBT2/DRIZZLESLAP/SQLBENCH/SYSBENCH command only.  Logs output of SHOW STATUS for each concurrency level. [default: %default]"
  )
parser.add_option(
    "--with-validation-server"
    , action= "store_true"
    , default= False
    , help="Flag to signal drizzle-automation to spin up a second server.  Used for randgen validations. [default: %default]"
    )

# Add all the BZR-mode-specific options
group= optparse.OptionGroup(parser, "Options when building/executing from a BZR repository/branch")

group.add_option(
    "-r"
  , "--bzr-revision"
  , metavar="REV"
  , help="A specific BZR revision that should be used in the automation run.  You can also specify a range of revisions similar to the way BZR does."
  )
group.add_option(
    "-s"
  , "--bzr-revision-step"
  , metavar="STEP"
  , help="If running a series of revisions, step STEP number of revisions between runs."
  )
group.add_option(
    "-b"
  , "--bzr-branch"
  , metavar="BRANCH"
  , help="Signals the automation runner to operate in a mode which builds and runs the appropriate server in a BZR branch.  The BZR branch that should be used in the automation run."
  )
group.add_option(
    "--bzr-repo-dir"
  , metavar="DIR"
  , help="The directory the main BZR repository root lives in."
  )
parser.add_option_group(group)

# Add all the MySQL Sandbox-mode-specific options
group= optparse.OptionGroup(parser, "Options when executing a stand-alone server using MySQL Sandbox")

group.add_option(
    "--mysql-sandbox"
  , metavar="MSB_NAME"
  , help="The name of the MySQL Sandbox for starting and stopping MySQL pre-built servers.  Using this option automatically sets the --no-bzr option to TRUE."
)
group.add_option(
    "--mysql-sandbox-dir"
  , metavar="DIR"
  , help="Where to find MySQL Sandboxes."
)
parser.add_option_group(group)


# Add all the MySQL Sandbox-mode-specific options
group= optparse.OptionGroup(parser, "Options when running reports")

group.add_option(
    "--report-name"
  , metavar="REPORT_NAME"
  , choices=['sysbench','dbt2','drizzleslap','sqlbench']
  , help="The name of the report you wish to run."
)
parser.add_option_group(group)

# supplied will be those arguments matching an option, 
# and __args will be everything else
(supplied, __args)= parser.parse_args()

# We assume the first arg is the command.  If it doesn't
# match any of the command names, we print the help screen
if len(__args) == 0:
  parser.print_help()
  sys.exit(0)
else:
  command= __args[0].lower()
  if command not in valid_commands:
    parser.print_help()
    sys.exit(0)

class RuntimeOptions:

  def __init__(self):
    global supplied
    global parser
    self._supplied= supplied
    self._parser= parser
    self._processing_mode= self.setProcessingMode()

  def getProcessingMode(self):
    """Returns the processing mode for the run"""
    if self._processing_mode is None:
      self.setProcessingMode()
    return self._processing_mode

  def setProcessingMode(self):
    """
Determines the overall build and processing mode based on arguments
supplied to the runner and any defaults.  The processing mode is 
important since it determines whether BZR is used, whether an 
automation sandbox is needed, or whether an external tool such as
MySQL Sandbox is responsible for controlling the server used in the
command run.
"""
    for key in dir(self._supplied):
      if key.startswith("mysql_sandbox"):
        if getattr(self._supplied, key) is not None:
          self._processing_mode= "mysqlsandbox"
          return
    self._processing_mode= "bzr"

  def processOptions(self, variables):
    """
Processes the command-line arguments/options and merges them into the
global array of configuration variables.  We override any configuration
variables passed to us after processing the configuration files with any
options specified on the command line.
"""
    if self._processing_mode == "mysqlsandbox":
      # Check MySQL Sandbox variables and options...
      pass
    elif self._processing_mode == "bzr":
      # We are using BZR and an automation sandbox so ensure all 
      # required configuration variables are found

      # Default assumes that the run is on the latest revision in the branch...
      variables['bzr_revision']= self._supplied.bzr_revision or 'last:1'

      # An interval of number of revisions to step/skip during run
      variables['bzr_revision_step']= self._supplied.bzr_revision_step or 1
      variables['bzr_revision_step']= int(variables['bzr_revision_step'])

      # Find our root repository directory
      variables['bzr_repo_dir']= self._supplied.bzr_repo_dir
      if variables['bzr_repo_dir'] is None:
        # No repo-dir specified.  We look for one in our configuration
        # file variables...
        try:
          default_keys= variables['defaults'].keys()
          for key in default_keys:
            if key in ['bzr-repo-dir','bzr_repo_dir','repo-dir','repo_dir','repository-dir','repository_dir']:
              variables['bzr_repo_dir']= variables['defaults'][key]
              break
          if not variables['bzr_repo_dir']:
            raise KeyError
        except KeyError:
          logging.error("""Couldn't find a root repository directory.
Suggestion: Add a bzr_repo_dir=DIR key/value pair to the [defaults] section of a configuration file,
or specify --bzr-repo-dir=DIR on the command line.""")
          sys.exit(1)

      # Find the branch we want to operate on
      variables['bzr_branch']= supplied.bzr_branch
      if variables['bzr_branch'] is None:
        # No branch specified. Look for a branch in the defaults section variables...
        try:
          default_keys= variables['defaults'].keys()
          for key in default_keys:
            if key in ['bzr-branch','bzr_branch','branch','branch-nick','branch_nick']:
              variables['bzr_branch']= variables['defaults'][key]
              break
          if not variables['bzr_branch']:
            raise KeyError
        except KeyError:
          logging.error("""Couldn't find a branch to operate on.
Suggestion: Add a bzr-branch=BRANCH key/value pair to the [defaults] section of a configuration file,
or specify --bzr-branch=BRANCH on the command line.""")
          sys.exit(1)

    # Find out where we should log output to
    variables['log_file']= supplied.log_file
    if variables['log_file'] is None:
      log_key_names= ['log_file','log-file']
      # No log-file specified. Look for a logging location for our specified
      # command, or defaults configuration section variables...
      all_keys= variables.keys()
      if variables['command'] in all_keys:
        for command_key in variables[variables['command']].keys():
          if command_key in log_key_names:
            variables['log_file']= variables[variables['command']][command_key]
            break
      else:
        try:
          default_keys= variables['defaults'].keys()
          for key in default_keys:
            if key in log_key_names:
              variables['log_file']= variables['defaults'][key]
              break
        except:
          pass
    if not variables['log_file']:
      variables['log_file']= 'stdout'


    # Add all our other options...
    others= ['dry_run',
             'engine',
             'force',
             'force_build',
             'ld_preload',
             'no_rsync',
             'no_store_db',
             'no_pull',
             'no_build',
             'profiler',
             'server',
             'report_name',
             'use_root_sandbox',
             'with_email_report',
             'with_show_status',
             'with_validation_server']
    for other in others:
      variables[other]= getattr(parser.values, other)

    if variables['ld_preload']:
      os.environ['LD_PRELOAD']= variables['ld_preload']
      logging.info("LD_PRELOAD is set to %s\n" % variables['ld_preload'])

    # For crashme, dbt2, drizzleslap, randgen, sqlbench and sysbench, we require that 
    # a configuration file with options is supplied at runtime...
    command_to_run= variables['command']
    if command_to_run in ['crashme', 'dbt2','drizzleslap','randgen', 'sqlbench','sysbench']:
      # Check to ensure we have a bench_config value...
      bench_config_name= supplied.bench_config_name
      if bench_config_name is None:
        logging.error("The --bench-config-name CLI option is required when running the %s command. Exiting." % command_to_run)
        sys.exit(1)
      else:
        variables['bench_config_name']= bench_config_name

    # Ensure reports have a report name specified
    if command_to_run == 'report':
      report_name= supplied.report_name
      if report_name is None:
        logging.error("The --report-name CLI option is required when running the REPORT command. Exiting.")
        sys.exit(1)
      else:
        variables['report_name']= report_name
        
        # Check to ensure we have a bench_config value for the specified report
        if report_name in ['dbt2','drizzleslap','sqlbench','sysbench']:
          bench_config_name= supplied.bench_config_name
          if bench_config_name is None:
            logging.error("The --bench-config CLI option is required when running the %s command. Exiting." % command_to_run)
            sys.exit(1)
          else:
            variables['bench_config_name']= bench_config_name

    return variables

options= RuntimeOptions()

