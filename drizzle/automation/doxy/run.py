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

"""Script to automate Doxygen code documentation."""

import sys
import os
import os.path
import re
from drizzle.automation.lib import logging
import commands

def execute(processing_mode, variables):
  # Set/verify some required variables, depending on the server
  # we are processing

  working_dir= variables['working_dir']
  run_date= datetime.datetime.now().isoformat()

  os.chdir(working_dir)

  logging.info("Processing Doxygen in \"%s\"." % working_dir)

  (retcode, output)= commands.getstatusoutput("doxygen")

  if not retcode == 0:
    logging.error("Doxygen failed.\nGot error: %s" % output)
    sys.exit(1)

  if variables['no_rsync'] is False:

    logging.info("Syncing Doxygen results.")

    try:
      ssh_user= variables['doxy']['ssh_user']
    except KeyError:
      ssh_user= variables['ssh']['ssh_user']

    try:
      rsync_dir= variables['doxy']['rsync_dir']
    except KeyError:
      rsync_dir= "drizzle.org:web/doxygen/"

    (retcode, output)= commands.getstatusoutput("rsync -avz %s@%s" % (ssh_user, rsync_dir))

    if not retcode == 0:
      logging.error("rsync failed.\nGot error: %s" % output)
      sys.exit(1)

  return True
