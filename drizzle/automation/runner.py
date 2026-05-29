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

"""The main automation script runner

The automation suite is a set of commands designed to ease the processing
of regression tests, code coverage tests, and benchmarking for Drizzle.

The drizzle-automation script is called with a command and some options.
The main runner script calls a command-specific runner to do its work.

There are currently two distinct code paths used by the automation runner, 
and they determine how a server is built, whether a source control system
is used to pull a revision/version of the server, and what controls the 
server:

  * Run a command against a server built from source in an "Automation Sandbox"

  This code path is used when the automation suite is processing a command
  on a branch of code contained in a BZR branch.  In order to facilitate 
  processing and saving results on a series of BZR revisions for a specific
  branch, the runner creates a Sandbox object.  The Sandbox uses BZR to 
  create a specific branch to run the automation command at a specified revision.

  For instance, assume a main BZR branch called "trunk", located at ~/repos/drizzle/trunk.

  If we wanted to run the "sysbench" command against this branch for revisions
  r930 through r932, we could call the drizzle-automation script like so:

  $> drizzle-automation --bench-config=some_benchmark_config --bzr-branch=trunk --r930..932 sysbench

  This would create 3 sandboxes:

    ~/repos/drizzle/trunk-sysbench-r930
    ~/repos/drizzle/trunk-sysbench-r931
    ~/repos/drizzle/trunk-sysbench-r932

  Each containing a version of the trunk BZR branch at a specific revision.  The sysbench command
  would be run in each sandbox, and each run would not build a server in a directory which 
  might be affected by another run.

  This is the default way of processing a command.  If any of the --bzr-xxxx options are 
  provided to the runner, it will use BZR and the automation sandbox to do its work.

  * Run a command against a pre-built server using MySQL Sandbox

  This code path is used when running an automation command against a *non-BZR*
  server.  This is necessary for testing or benchmarking pre-built binaries or servers
  installed in something like MySQL Sandbox, and no BZR commands are relevant to the
  automation run.

  When the --mysql-sandbox-xxxx options are provided to the automation runner, the
  runner will not build a server from source or create an automation sandbox.  Instead,
  it will perform the command using MySQL Sandbox to start, stop, and control the server.
"""

# Note that much of this originally was a shell script, and so it's
# not particularly "Pythonic".  Much help is needed to get the code
# more structured and pretty!

import sys
import os
from drizzle.automation.lib import logging

try:
  from drizzle.automation import lib
except ImportError, e:
  sys.stderr.write("ERROR: Couldn't import automation library. Please check the directory containing the automation library is on your PYTHONPATH.\n")
  sys.exit(1)

from drizzle.automation.lib import options
from drizzle.automation.lib import config
from drizzle.automation.lib import util

def run():
  # Container for all our configuration and option arguments. 
  variables= {}
  
  # Process our command first
  variables['command']= options.command.lower()
  
  # Merge in our configuration file variables
  variables= config.process_config(variables)
  
  # Figure out which mode we'll be operating in...
  processing_mode= options.options.getProcessingMode()
  
  # Merge/override with CLI options
  variables= options.options.processOptions(variables)
  
  # Setup our logging facilities
  logging.setOutput(variables['log_file'])
  
  # In dry-run mode, print a list of the configuration variables found
  # @TODO Make this nicer and more robust...
  if variables['dry_run']:
    util.pretty_print_configuration(variables)
    sys.exit(0)
  
  # Here, we set the runner script based on the 
  # command specified...
  
  command= variables['command'] # lib/options.py ensures we have a command specified...
  
  from drizzle.automation.lib import db
  db.init(variables)    # Checks dependencies and required configuration variables for the DB...

  # Report command is different because we don't need to build
  # a server.  All we do is query the database...
  # Note that variables['report_name'] is validated in options.py
  if command == 'report':
    from drizzle.automation.reports import run as runner
    result= runner.execute(variables['report_name'], variables)
    if not result:
      logging.error("Failed to execute report. Exiting.")
      sys.exit(1)
    else:
      sys.exit(0)
  
  # All the below commands trigger a build of the server via source
  # or a sandbox.
  if command == 'sloc':
    from drizzle.automation.sloc import run as runner
  elif command == 'crashme':
    from drizzle.automation.crashme import run as runner
  elif command in ('doxy','doxygen'):
    from drizzle.automation.doxy import run as runner
  elif command in ('dbt2'):
    from drizzle.automation.dbt2 import run as runner
  elif command in ('drizzleslap','slap'):
    from drizzle.automation.drizzleslap import run as runner
  elif command == 'lcov':
    from drizzle.automation.lcov import run as runner
  elif command in ('randgen'):
    from drizzle.automation.randgen import run as runner
  elif command == 'sqlbench':
    from drizzle.automation.sqlbench import run as runner
  elif command == 'sysbench':
    from drizzle.automation.sysbench import run as runner
  
  # OK, so we've parsed our basic configuration variables and options
  # at this point.  Now, we need to figure out what code path we need
  # to take.  When operating on a BZR branch, we use an automation 
  # sandbox and supply the command runner with the root directory of the
  # automation sandbox.
  from drizzle.automation.lib import sandbox
  
  if processing_mode == "bzr":
  
    # If we're here, we are guaranteed to have all our required 
    # configuration variables, so localize the required ones to
    # make calling subroutines a little cleaner...
    repo_dir= variables['bzr_repo_dir']
    branch= variables['bzr_branch']
    revision= variables['bzr_revision']
    revision_step= variables['bzr_revision_step']
    no_pull_flag= variables['no_pull']
    use_root_sandbox_flag= variables['use_root_sandbox']
  
    # We now set up our sandbox for the run.  The sandbox always requires
    # the following information, supplied either as CLI options or pulled
    # from configuration files:
    #  * repository directory         (--repo-dir)    or [defaults][repo-dir]
    #  * command
    #  * branch nickname              (--branch)      or [defaults][branch]
    #  * revision we wish to process  (--revision)
    #
    # Since a range of revisions may be specified, we want to establish one
    # sandbox per tuple of the above elements.  The sandbox is really just
    # a directory containing a bzr branch from the parent --branch-dir where
    # the automation process can do its work in isolation from other runs
  
    # TODO: Separate this out so that we can deal with revision ranges
    root_sandbox= sandbox.RootSandbox(repo_dir, branch)
    root_sandbox.create(no_pull_flag, use_root_sandbox_flag)

    revision_range= root_sandbox.get_revision_range(revision, revision_step)

    # OK, so for each revision create an automation sandbox and execute our runner
    for revision in revision_range:

      # if we are going to use just the root sandbox to build in we then don't
      # need to create the sandbox command branch and the sandbox revision branch
      # just go ahead and set the working_dir
      if use_root_sandbox_flag is True:
        variables['working_dir']= repo_dir
      else:
        rev_sandbox= sandbox.Sandbox(command, root_sandbox, revision)
        rev_sandbox.create()
        variables['working_dir']= rev_sandbox.get_working_dir()

      variables['bzr_revision']= revision
  
      logging.info("Running %s at %s" % (processing_mode,variables['working_dir']))
      result= runner.execute(processing_mode, variables)
      if not result:
        if variables['force'] is True:
          pass
        else:
          logging.error("Failed to execute runner in sandbox: \"%s\". Exiting." % branch_dir)
          sys.exit(1)
  
  else:
  
    # This code path is run when we are processing commands against pre-built
    # binaries or servers not in a BZR branch.
  
    variables['working_dir']= os.path.join(repo_dir, branch)
    results= runner.execute(processing_mode, variables)
    if not results:
      logging.error("Failed to execute runner in: \"%s\". Exiting." % branch_dir)
      sys.exit(1)

if __name__== '__main__':
  run()
