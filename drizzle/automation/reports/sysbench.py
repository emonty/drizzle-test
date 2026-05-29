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

"""Various reports on sysbench command results"""

import os
from drizzle.automation.lib import db
import socket
import commands

def get5and20RevisionRanges(bench_config_name, server_name, bzr_branch, run_id):
  """Return a tuple with 2 ranges of run_id values for the last 5 and 20 runs"""
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

  return (last_5_revs, last_20_revs)

def getRegressionOverRange(run_id, range):
  sql= """
SELECT 
  i.concurrency
, ROUND(AVG(i.tps), 2) AS tps
, IF (AVG(i.tps) >= agg.avg_tps
  , CONCAT('+', ROUND(((AVG(i.tps) - agg.avg_tps) / agg.avg_tps) * 100, 2), '%%') 
  , CONCAT('-', ROUND(((agg.avg_tps - AVG(i.tps)) / agg.avg_tps) * 100, 2), '%%')
  ) as pct_diff_from_avg
, ROUND((AVG(i.tps) - agg.avg_tps), 2) as diff_from_avg
, ROUND(agg.min_tps, 2) AS min_tps
, ROUND(agg.max_tps, 2) AS max_tps
, ROUND(agg.avg_tps, 2) AS avg_tps
, FORMAT(ROUND(agg.stddev_tps, 2),2) AS stddev_tps
FROM bench_config c
NATURAL JOIN bench_runs r
NATURAL JOIN sysbench_run_iterations i
INNER JOIN (
  SELECT
    concurrency
  , MIN(tps) as min_tps
  , MAX(tps) as max_tps
  , AVG(tps) as avg_tps
  , STDDEV(tps) as stddev_tps
  FROM sysbench_run_iterations iter
  WHERE run_id IN (%s)
  GROUP BY concurrency
) AS agg
  ON i.concurrency = agg.concurrency
WHERE r.run_id = %d
GROUP BY i.concurrency
ORDER BY i.concurrency
      """ % (
        ",".join(range)
      , run_id
      )
  return db.get_select(sql)

def getAllRegressionForBranchAndConfig(bench_config_name, server_name, bzr_branch, run_id):
  sql= """
SELECT 
  i.concurrency
, ROUND(AVG(i.tps), 2) AS tps
, IF (AVG(i.tps) >= agg.avg_tps
  , CONCAT('+', ROUND(((AVG(i.tps) - agg.avg_tps) / agg.avg_tps) * 100, 2), '%%') 
  , CONCAT('-', ROUND(((agg.avg_tps - AVG(i.tps)) / agg.avg_tps) * 100, 2), '%%')
  ) as pct_diff_from_avg
, ROUND((AVG(i.tps) - agg.avg_tps), 2) as diff_from_avg
, ROUND(agg.min_tps, 2) AS min_tps
, ROUND(agg.max_tps, 2) AS max_tps
, ROUND(agg.avg_tps, 2) AS avg_tps
, FORMAT(ROUND(agg.stddev_tps, 2),2) AS stddev_tps
FROM bench_config c
NATURAL JOIN bench_runs r
NATURAL JOIN sysbench_run_iterations i
INNER JOIN (
  SELECT
    iter.concurrency
  , MIN(tps) as min_tps
  , MAX(tps) as max_tps
  , AVG(tps) as avg_tps
  , STDDEV(tps) as stddev_tps
  FROM bench_config conf
  NATURAL JOIN bench_runs runs
  NATURAL JOIN sysbench_run_iterations iter
  WHERE conf.name = '%s'
  AND runs.server = '%s'
  AND runs.version LIKE '%s%%'
  GROUP BY iter.concurrency
) AS agg
  ON i.concurrency = agg.concurrency
WHERE r.run_id = %d
GROUP BY i.concurrency
ORDER BY i.concurrency
      """ % (
        bench_config_name
      , server_name
      , bzr_branch
      , run_id
      )

  return db.get_select(sql)

def getSysbenchRegressionReportForRunId(run_id, bench_config_name, server_name, bzr_branch, bzr_revision):
  """Returns a textual report of the regression over a series of runs given a supplied run ID"""
  
  (last_5_revs, last_20_revs)= get5and20RevisionRanges(bench_config_name, server_name, bzr_branch, run_id)
  
  report_text= """====================================================================================================
REGRESSION REPORT
====================================================================================================
MACHINE:  %s
RUN ID:   %d
WORKLOAD: %s
SERVER:   %s
VERSION:  %s
REVISION: %d
====================================================================================================

TRENDING OVER LAST 5 runs

""" % (
    socket.gethostname()
  , run_id
  , bench_config_name
  , server_name
  , bzr_branch
  , int(bzr_revision)
)

  report_text= report_text + "%-6s %-7s %-17s %-10s %-10s %-10s %-10s %-10s" % ("Conc","TPS","% Diff from Avg","Diff","Min","Max","Avg","STD")
  report_text= report_text + """
====================================================================================================
"""
  if len(last_5_revs) > 0:
    results= getRegressionOverRange(run_id, last_5_revs)
    for result in results:
      report_text= report_text + "%-6s %6s %12s %10s %10s %10s %10s %10s\n" % tuple(result)

    report_text= report_text + """====================================================================================================

TRENDING OVER Last 20 runs

"""
    report_text= report_text + "%-6s %-7s %-17s %-10s %-10s %-10s %-10s %-10s" % ("Conc","TPS","% Diff from Avg","Diff","Min","Max","Avg","STD")
    report_text= report_text + """
====================================================================================================
"""
  if len(last_20_revs) > 0:
    results= getRegressionOverRange(run_id, last_20_revs)
    for result in results:
      report_text= report_text + "%-6s %6s %12s %10s %10s %10s %10s %10s\n" % tuple(result)

    report_text= report_text + """====================================================================================================

TRENDING OVER ALL runs

"""
    report_text= report_text + "%-6s %-7s %-17s %-10s %-10s %-10s %-10s %-10s" % ("Conc","TPS","% Diff from Avg","Diff","Min","Max","Avg","STD")
    report_text= report_text + """
====================================================================================================
"""

  results= getAllRegressionForBranchAndConfig(bench_config_name, server_name, bzr_branch, run_id)
  for result in results:
    report_text= report_text + "%-6s %6s %12s %10s %10s %10s %10s %10s\n" % tuple(result)
  report_text= report_text + "===================================================================================================="

  return report_text

def getSysbenchRegressionReport(working_dir, bench_config_name, run_id, run_date, server_name, bzr_branch, bzr_revision):
  """Returns a textual report of the regression over a series of runs"""

  # Find the revision comment from BZR
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

  # As non-staging branches often have little to no historical data,  
  # these reports can be useless.  To correct this, we compare to
  # the staging branch and make some minor changes to the report
  # to let people know how the numbers were produced
  # we only need to change bzr_branch's value to staging to 
  # alter what we are comparing against 
  staging_branch = 'staging'
  report_branch_name = bzr_branch # we may change bzr_branch, so we keep orig. name for reports
  if bzr_branch != staging_branch:
      report_notation    = ' compared to %s historical data' %(staging_branch) 
      bzr_branch         = staging_branch
  else:
      report_notation = ''  

  (last_5_revs, last_20_revs)= get5and20RevisionRanges(bench_config_name, server_name, bzr_branch, run_id)
  
  report_text= """====================================================================================================
SYSBENCH BENCHMARK REPORT %s
====================================================================================================
MACHINE:  %s
RUN ID:   %d
RUN DATE: %s
WORKLOAD: %s
SERVER:   %s
VERSION:  %s
REVISION: %d
COMMENT:  %s
====================================================================================================

TRENDING OVER LAST 5 runs %s
""" % (
    report_notation
  , socket.gethostname()
  , run_id
  , run_date
  , bench_config_name
  , server_name
  , report_branch_name 
  , int(bzr_revision)
  , rev_comment
  , report_notation
)

  report_text= report_text + "%-6s %-7s %-17s %-10s %-10s %-10s %-10s %-10s" % ("Conc","TPS","% Diff from Avg","Diff","Min","Max","Avg","STD")
  report_text= report_text + """
====================================================================================================
"""
  if len(last_5_revs) > 0:
    results= getRegressionOverRange(run_id, last_5_revs)
    for result in results:
      report_text= report_text + "%-6s %6s %12s %10s %10s %10s %10s %10s\n" % tuple(result)
    report_text= report_text + """====================================================================================================

TRENDING OVER Last 20 runs %s

""" % (
    report_notation
)

  report_text= report_text + "%-6s %-7s %-17s %-10s %-10s %-10s %-10s %-10s" % ("Conc","TPS","% Diff from Avg","Diff","Min","Max","Avg","STD")
  report_text= report_text + """
====================================================================================================
"""
  if len(last_20_revs) > 0:
    results= getRegressionOverRange(run_id, last_20_revs)
    for result in results:
      report_text= report_text + "%-6s %6s %12s %10s %10s %10s %10s %10s\n" % tuple(result)

    report_text= report_text + """====================================================================================================

TRENDING OVER ALL runs %s

""" % (
    report_notation
)
    report_text= report_text + "%-6s %-7s %-17s %-10s %-10s %-10s %-10s %-10s" % ("Conc","TPS","% Diff from Avg","Diff","Min","Max","Avg","STD")
    report_text= report_text + """
====================================================================================================
"""

  results= getAllRegressionForBranchAndConfig(bench_config_name, server_name, bzr_branch, run_id)
  for result in results:
    report_text= report_text + "%-6s %6s %12s %10s %10s %10s %10s %10s\n" % tuple(result)
  report_text= report_text + "===================================================================================================="

  if full_commentary:
    report_text= report_text + """
FULL REVISION COMMENTARY:

%s""" % full_commentary
  return report_text
