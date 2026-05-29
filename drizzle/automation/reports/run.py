#! /usr/bin/python
# -*- mode: python; c-basic-offset: 2; indent-tabs-mode: nil; -*-
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

"""Script to automate running of reports."""

import sys
import socket
import os
import os.path
from drizzle.automation.lib import logging
from drizzle.automation.lib import util
from drizzle.automation.lib import db
import commands
import re
import time
import datetime

# Email or display the report
def email_or_display_report(email_flag, email_string, report_string, report_text, bzr_revision, run_id):
  if email_flag is True:
    # bug https://bugs.launchpad.net/launchpad/+bug/419562 - need to use registered launchpad name for from
    #from_string= ('%s <drizzle-benchmark@lists.launchpad.net>' % socket.gethostname())
    from_string= ('%s <hudson@inaugust.com>' % socket.gethostname())
    util.mail(from_string, email_string, "%s Report for Build %d and Run ID %d" % (report_string, int(bzr_revision), int(run_id)), report_text)
  else:
    print report_text

def execute(report_name, variables):
  # Verify configuration variables and run the requested report

  # We need a server, a revision, and a branch
  try:
    bzr_revision= variables['bzr_revision']
    bzr_branch= variables['bzr_branch']
  except KeyError:
    logging.error("The report option requires the --bzr-revision, --bzr-branch CLI options to be supplied. Exiting.")
    return False

  # For reports, we need a config file, a server, a revision, and a branch
  try:
    bench_config_name= variables['bench_config_name']
  except KeyError:
    logging.error("The %s report requires the --bench-config-name, --bzr-revision, --bzr-branch CLI options to be supplied. Exiting." % report_name)
    return False

  try:
    server_name= variables['server']
  except KeyError:
    server_name= 'drizzled'

  if report_name == 'sysbench':
    import drizzle.automation.reports.sysbench as reports
    run_id= util.getLastRunId(bench_config_name, server_name, variables['bzr_branch'], int(variables['bzr_revision']))
    if run_id is None:
      logging.error("Could not find the last run ID for config %s, server %s, branch %s at revision %s. Exiting."
         % (
              bench_config_name
            , server_name
            , variables['bzr_branch']
            , variables['bzr_revision']
           ))
      sys.exit(1)
    report_text= reports.getSysbenchRegressionReportForRunId(run_id, bench_config_name, server_name, variables['bzr_branch'], int(variables['bzr_revision']))
    email_or_display_report(variables['with_email_report'], variables['sysbench']['report_email'], 'SYSBENCH', report_text, bzr_revision, run_id)

  elif report_name == 'sqlbench':
    import drizzle.automation.reports.sqlbench as reports
    run_id= util.getLastRunId(bench_config_name, server_name, variables['bzr_branch'], int(variables['bzr_revision']))
    if run_id is None:
      logging.error("Could not find the last run ID for config %s, server %s, branch %s at revision %s. Exiting."
         % (
              bench_config_name
            , server_name
            , variables['bzr_branch']
            , variables['bzr_revision']
           ))
      sys.exit(1)
    report_text= reports.getSqlbenchReport(None, bench_config_name, run_id, 'N/A', server_name, variables['bzr_branch'], int(variables['bzr_revision']), variables['engine'])
    email_or_display_report(variables['with_email_report'], variables['sqlbench']['report_email'], 'SQLBENCH', report_text, bzr_revision, run_id)

  elif report_name == 'drizzleslap':
    import drizzle.automation.reports.drizzleslap as reports
    run_id= util.getLastRunId(bench_config_name, server_name, variables['bzr_branch'], int(variables['bzr_revision']))
    if run_id is None:
      logging.error("Could not find the last run ID for config %s, server %s, branch %s at revision %s. Exiting."
         % (
              bench_config_name
            , server_name
            , variables['bzr_branch']
            , variables['bzr_revision']
           ))
      sys.exit(1)
    report_text= reports.getDrizzleslapReport(None, bench_config_name, run_id, 'N/A', server_name, variables['bzr_branch'], int(variables['bzr_revision']))
    email_or_display_report(variables['with_email_report'], variables['drizzleslap']['report_email'], 'DRIZZLESLAP', report_text, bzr_revision, run_id)

  elif report_name == 'dbt2':
    import drizzle.automation.reports.dbt2 as reports
    run_id= util.getLastRunId(bench_config_name, server_name, variables['bzr_branch'], int(variables['bzr_revision']))
    if run_id is None:
      logging.error("Could not find the last run ID for config %s, server %s, branch %s at revision %s. Exiting."
         % (
              bench_config_name
            , server_name
            , variables['bzr_branch']
            , variables['bzr_revision']
           ))
      sys.exit(1)
    report_text= reports.getDbt2Report(None, bench_config_name, run_id, 'N/A', server_name, variables['bzr_branch'], int(variables['bzr_revision']))
    email_or_display_report(variables['with_email_report'], variables['dbt2']['report_email'], 'DBT2', report_text, bzr_revision, run_id)

  else: 
    logging.error("Invalid report option %s. Must be dbt2, drizzleslap, sqlbench or sysbench", report_name)
    return False

  return True
