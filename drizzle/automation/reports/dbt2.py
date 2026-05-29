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

"""Various reports on dbt2 command results"""

import os
from drizzle.automation.lib import db
import socket
import commands


def sqlQueryString(last_revs, run_id):
  sql= """
SELECT 
  i.connections
, ROUND(AVG(i.tpm),2) AS tpm
, IF (AVG(i.tpm) >= agg.avg_tpm
  , CONCAT('+', ROUND(((AVG(i.tpm) - agg.avg_tpm) / agg.avg_tpm) * 100, 2), '%%')
  , CONCAT('-', ROUND(((agg.avg_tpm - AVG(i.tpm)) / agg.avg_tpm) * 100, 2), '%%')
  ) as pct_diff_from_avg
, ROUND((AVG(i.tpm) - agg.avg_tpm), 2) AS diff_from_avg
, ROUND(agg.min_tpm,2) AS min_tpm
, ROUND(agg.max_tpm,2) AS max_tpm
, ROUND(agg.avg_tpm,2) AS avg_tpm
, FORMAT(ROUND(agg.stddev_tpm,2),2) AS stddev_tpm
FROM bench_config c
NATURAL JOIN bench_runs r
NATURAL JOIN dbt2_run_iterations i
INNER JOIN (
  SELECT
    connections
  , MIN(tpm) as min_tpm
  , MAX(tpm) as max_tpm
  , AVG(tpm) as avg_tpm
  , STDDEV(tpm) as stddev_tpm
  FROM dbt2_run_iterations iter
  WHERE run_id IN (%s)
  GROUP BY connections
) AS agg
  ON i.connections= agg.connections
WHERE r.run_id = %d
GROUP BY i.connections
ORDER BY i.connections
      """ % (
        ",".join(last_revs)
      , run_id
      )

  return db.get_select(sql)

def printResults(results, report_text):
  """ Print out the sql results for a query """

  for result in results:
    if result[1] != "TOTALS":
      report_text= report_text + "%-7s %9s %10s %9s %7s %7s %7s %7s\n" % tuple(result)
  return report_text

# Returns header information for each section
def printHeader(string, report_text):
  report_text= report_text + """
================================================================================================
TRENDING OVER %s
""" % (string)

  report_text= report_text + "%-11s %-5s %-14s %-7s %-7s %-7s %-7s %-7s" % ("Connections","TPM","% Diff from Avg","Diff","Min","Max","Avg","STD")

  report_text= report_text + """
================================================================================================
"""
  return report_text

def getDbt2Report(working_dir, bench_config_name, run_id, run_date, server_name, bzr_branch, bzr_revision):
  """Returns a textual report of the regression over a series of runs"""

  # Find the revision comment from BZR
  if working_dir != None:
    os.chdir(working_dir)
    (retcode, rev_comment_output)= commands.getstatusoutput("bzr log -r-1 -n0 --line")

  # Output from above command looks like this:
  # jpipes@serialcoder:~/repos/drizzle/trunk-sysbench-r1046$ bzr log -r-1 -n0 --line
  # 1046: Brian Aker 2009-05-31 [merge] Merge Jay.
  # 1039.2.9: Jay Pipes 2009-05-31 Tiny cleanups
  # 1039.2.8: Jay Pipes 2009-05-31 Yet more indentation and style cleanup
  # 1039.2.7: Jay Pipes 2009-05-31 Yet more style and indentation cleanups.
  # 1039.2.6: Jay Pipes 2009-05-31 No code changes...only indentation and style cleanup.

    comment_lines= rev_comment_output.split("\n")
    rev_comment= comment_lines[0]
    if len(comment_lines) > 1:
      full_commentary= "\n".join(comment_lines[1:])
    else:
      full_commentary= None
  else:
      rev_comment= "N/A"
      full_commentary= None

  sql= """
SELECT 
  run_id
FROM bench_config c
NATURAL JOIN bench_runs r
WHERE c.name = '%s'
AND r.server = '%s'
AND r.version LIKE '%s%%'
AND r.run_id <= %d
ORDER BY run_id DESC
LIMIT 20
""" % (
        bench_config_name
      , server_name
      , bzr_branch
      , run_id
      )
  results= db.get_select(sql)

  last_5_revs= []
  last_20_revs= []
  x= 0
  for result in results:
    cur_run_id= int(result[0])
    if x < 5:
      last_5_revs.append(str(cur_run_id))
    last_20_revs.append(str(cur_run_id))
    x= x + 1

  report_text= """=======================================================================================
DBT2 REPORT
=======================================================================================
MACHINE:  %s
RUN ID:   %d
RUN DATE: %s
SERVER:   %s
VERSION:  %s
REVISION: %d
COMMENT:  %s
""" % (
    socket.gethostname()
  , run_id
  , run_date
  , server_name
  , bzr_branch
  , int(bzr_revision)
  , rev_comment
)

  if len(last_5_revs) > 0:
    report_text= printHeader('LAST 5 runs', report_text)
    results= sqlQueryString(last_5_revs, run_id)
    report_text= printResults(results, report_text)

  if len(last_20_revs) > 0:
    report_text= printHeader('LAST 20 runs', report_text)
    results= sqlQueryString(last_20_revs, run_id)
    report_text= printResults(results, report_text)

    report_text= printHeader('ALL runs', report_text)

    sql= """
SELECT 
  i.connections
, ROUND(AVG(i.tpm),2) AS tpm
, IF (AVG(i.tpm) >= agg.avg_tpm
  , CONCAT('+', ROUND(((AVG(i.tpm) - agg.avg_tpm) / agg.avg_tpm) * 100, 2), '%%')
  , CONCAT('-', ROUND(((agg.avg_tpm- AVG(i.tpm)) / agg.avg_tpm) * 100, 2), '%%')
  ) as pct_diff_from_avg
, ROUND((AVG(i.tpm) - agg.avg_tpm), 2) AS diff_from_avg
, ROUND(agg.min_tpm,2) AS min_tpm
, ROUND(agg.max_tpm,2) AS max_tpm
, ROUND(agg.avg_tpm,2) AS avg_tpm
, FORMAT(ROUND(agg.stddev_tpm,2),2) AS stddev_tpm
FROM bench_config c
NATURAL JOIN bench_runs r
NATURAL JOIN dbt2_run_iterations i
INNER JOIN (
  SELECT
    iter.connections
  , MIN(tpm) as min_tpm
  , MAX(tpm) as max_tpm
  , AVG(tpm) as avg_tpm
  , STDDEV(tpm) as stddev_tpm
  FROM bench_config conf
  NATURAL JOIN bench_runs runs
  NATURAL JOIN dbt2_run_iterations iter
  WHERE conf.name = '%s'
  AND runs.server = '%s'
  AND runs.version LIKE '%s%%'
  GROUP BY iter.connections
) AS agg
  ON i.connections= agg.connections
WHERE r.run_id = %d
GROUP BY i.connections
ORDER BY i.connections
      """ % (
        bench_config_name
      , server_name
      , bzr_branch
      , run_id
      )

    results= db.get_select(sql)

    report_text= printResults(results, report_text)
    report_text= report_text + """
========================================================================================================================="""

  if full_commentary:
    report_text= report_text + """
FULL REVISION COMMENTARY:

%s""" % full_commentary
  return report_text
