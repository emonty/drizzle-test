#! /usr/bin/python
# -*- mode: python; c-basic-offset: 2; indent-tabs-mode: nil; -*-
# vim:expandtab:shiftwidth=2:tabstop=2:smarttab:
#
# Copyright (C) 2009 Sun Microsystems
#
# Authors:
#
#  Jay Pipes <joinfu@sun.com>
#  Lee Bieber<lee.bieber@sun.com>
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

"""Various reports on drizzleslap command results"""

import os
from drizzle.automation.lib import db
import socket
import commands

def sqlQueryString(last_revs, run_id):
  sql= """
SELECT 
  i.engine_name
, i.test_name
, i.concurrency
, FORMAT(AVG(i.total_time),3) AS total_time
, IF (AVG(i.total_time) >= agg.avg_total_time
  , CONCAT('-', ROUND(((AVG(i.total_time) - agg.avg_total_time) / agg.avg_total_time) * 100, 2), '%%')
  , CONCAT('+', ROUND(((agg.avg_total_time - AVG(i.total_time)) / agg.avg_total_time) * 100, 2), '%%')
  ) as pct_diff_from_avg
, ROUND((AVG(i.total_time) - agg.avg_total_time), 2) AS diff_from_avg
, FORMAT(agg.min_total_time,3) AS min_total_time
, FORMAT(agg.max_total_time,3) AS max_total_time
, FORMAT(agg.avg_total_time,3) AS avg_total_time
, FORMAT(agg.stddev_total_time,3) AS stddev_total_time
FROM bench_config c
NATURAL JOIN bench_runs r
NATURAL JOIN drizzleslap_run_iterations i
INNER JOIN (
  SELECT
    test_name
  , MIN(total_time) as min_total_time
  , MAX(total_time) as max_total_time
  , AVG(total_time) as avg_total_time
  , STDDEV(total_time) as stddev_total_time
  FROM drizzleslap_run_iterations iter
  WHERE run_id IN (%s)
  GROUP BY engine_name, test_name, concurrency
) AS agg
  ON i.test_name = agg.test_name
WHERE r.run_id = %d
GROUP BY i.engine_name, i.test_name, i.concurrency
ORDER BY i.engine_name, i.test_name, i.concurrency
      """ % (
        ",".join(last_revs)
      , run_id
      )

  return db.get_select(sql)

def printResults(results, report_text):
  """ Print out the sql results for a query """

  for result in results:
    report_text= report_text + "%-10s %-26s %-5s %8s %8s %10s %8s %8s %8s %8s\n" % tuple(result)
  return report_text

def printHeader(string, report_text):
  """Returns header information for each section """
  report_text= report_text + """
======================================================================================================================
TRENDING OVER %s
""" % (string)

  report_text= report_text + "%-10s %-25s %-8s %-5s %-13s %-7s %-8s %-8s %-8s %-8s" % ("Engine", "Test","Conc","Time","% Diff from Avg","Diff","Min","Max","Avg","STD")

  report_text= report_text + """
======================================================================================================================
"""


  return report_text

def getDrizzleslapReport(working_dir, bench_config_name, run_id, run_date, server_name, bzr_branch, bzr_revision):
  """Returns a textual report of the results over a series of runs"""

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
  # 1039.2.5: Jay Pipes 2009-05-31 Style cleanups and moves JOIN_TAB definition out into its own header.
  # 1039.2.4: Jay Pipes 2009-05-31 Tiny indentation cleanup.

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

  report_text= """=================================================================================================
DRIZZLESLAP REPORT
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

  report_text= printHeader('LAST 5 runs', report_text)
  results= sqlQueryString(last_5_revs, run_id)
  report_text= printResults(results, report_text)

  report_text= printHeader('LAST 20 runs', report_text)
  results= sqlQueryString(last_20_revs, run_id)
  report_text= printResults(results, report_text)

  report_text= printHeader('ALL runs', report_text)

  sql= """
SELECT 
  i.engine_name
, i.test_name
, i.concurrency
, FORMAT(AVG(i.total_time),3) AS total_time
, IF (AVG(i.total_time) >= agg.avg_total_time
  , CONCAT('-', ROUND(((AVG(i.total_time) - agg.avg_total_time) / agg.avg_total_time) * 100, 2), '%%')
  , CONCAT('+', ROUND(((agg.avg_total_time - AVG(i.total_time)) / agg.avg_total_time) * 100, 2), '%%')
  ) as pct_diff_from_avg
, ROUND((AVG(i.total_time) - agg.avg_total_time), 2) as diff_from_avg
, FORMAT(agg.min_total_time,3) AS min_total_time
, FORMAT(agg.max_total_time,3) AS max_total_time
, FORMAT(agg.avg_total_time,3) AS avg_total_time
, FORMAT(agg.stddev_total_time,3) AS stddev_total_time
FROM bench_config c
NATURAL JOIN bench_runs r
NATURAL JOIN drizzleslap_run_iterations i
INNER JOIN (
  SELECT
    iter.test_name
  , MIN(total_time) as min_total_time
  , MAX(total_time) as max_total_time
  , AVG(total_time) as avg_total_time
  , STDDEV(total_time) as stddev_total_time
  FROM bench_config conf
  NATURAL JOIN bench_runs runs
  NATURAL JOIN drizzleslap_run_iterations iter
  WHERE conf.name = '%s'
  AND runs.server = '%s'
  AND runs.version LIKE '%s%%'
  GROUP BY iter.engine_name, iter.test_name, iter.concurrency
) AS agg
  ON i.test_name = agg.test_name
WHERE r.run_id = %d
GROUP BY i.engine_name, i.test_name, i.concurrency
ORDER BY i.engine_name, i.test_name, i.concurrency
      """ % (
        bench_config_name
      , server_name
      , bzr_branch
      , run_id
      )

  results= db.get_select(sql)
  report_text= printResults(results, report_text)
  report_text= report_text + """======================================================================================================================
"""

  if full_commentary:
    report_text= report_text + """
FULL REVISION COMMENTARY:

%s""" % full_commentary
  return report_text
