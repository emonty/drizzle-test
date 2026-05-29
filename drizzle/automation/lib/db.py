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

import commands
from drizzle.automation.lib  import logging
import sys
import os
import random

# Local variables
_mysql_user= ""
_mysql_pass= ""
_mysql_host= ""
_db_name= ""
_use_db= ""

def init(variables):
  global _mysql_user
  global _mysql_pass
  global _mysql_host
  global _db_name
  global _use_db
  try:
    _mysql_user= variables['db']['mysql_user']
    _mysql_pass= variables['db']['mysql_pass']
    _mysql_host= variables['db']['mysql_host']
    _db_name= variables['db']['db_name']
    _use_db= variables['db']['use_db']
  except:
    logging.error("Failed to find the required stats section in a configuration file.")
    sys.exit(1)

def execute_sql(sql):
  global _mysql_user
  global _mysql_pass
  global _mysql_host
  global _db_name
  global _use_db


  if _use_db == 'drizzle':
    import MySQLdb
    db=MySQLdb.connect(host="127.0.0.1",db=_db_name,port=4427)
    c=db.cursor()
    try:
      c.execute(sql)
    except Exception, e:
      logging.error("SQL Execution error executing SQL:\n%s" % (sql))
      logging.error("Encountered error: %s %s" %(Exception, e))
      db.close()
      sys.exit(1)

    db.commit()
    db.close()

  else:   # else assume we are using mysql
    # We create a temporary file in the directory and stream the supplied
    # SQL from that file. This gets us around a dependency on MySQLdb for now
    filename= "sqlfile%d" % random.randint(0,100000)
    f= open(filename, "w+b")
    f.write(sql)
    f.flush()
    f.close()
    (retcode, output)= commands.getstatusoutput("mysql --user=%s --password=%s --host=%s %s < %s" % (_mysql_user, _mysql_pass, _mysql_host, _db_name, filename))

    if not retcode == 0:
      logging.error("SQL Execution error executing SQL:\n%s\n%s" % (sql, output))
      os.unlink(filename)
      sys.exit(1)

    os.unlink(filename)

def get_select(sql):
  global _mysql_user
  global _mysql_pass
  global _mysql_host
  global _db_name
  global _use_db

  if _use_db == 'drizzle':
    import MySQLdb
    db=MySQLdb.connect(host="127.0.0.1",db=_db_name,port=4427)
    try:
      db.query(sql)
    except:
      logging.error("SQL Execution error executing SQL:\n%s" % (sql))
      db.close()
      sys.exit(1)

    rows= db.store_result()
    result= []
    for row in rows.fetch_row(maxrows=0):
      result.append(row)

    db.close

  else:    # else assume we are using mysql
    (retcode, output)= commands.getstatusoutput("mysql --user=%s --password=%s --host=%s %s -e\"%s\"" % (_mysql_user, _mysql_pass, _mysql_host, _db_name, sql))
    if not retcode == 0:
      logging.error("SQL Execution error executing SQL:\n%s\n%s" % (sql, output))
      sys.exit(1)

    # First line is the fields...
    lines= output.split("\n")
    result= []
    fields= lines[0].split("\t")
    lineno= 0
    for line in lines[1:]:
      data_fields= line.split("\t")
      cur_data= data_fields
      result.append(cur_data)
      
  return result

def create_tables():
  create_sql= """
CREATE TABLE sloc_stats (
  server VARCHAR(20) NOT NULL
, version VARCHAR(50) NOT NULL
, directory VARCHAR(50) NOT NULL
, language VARCHAR(20) NOT NULL
, run_date DATETIME NOT NULL
, count INT NOT NULL
, PRIMARY KEY (server, version, directory, language)
) ENGINE=InnoDB;

CREATE TABLE lcov_stats (
  server VARCHAR(20) NOT NULL
, version VARCHAR(50) NULL
, run_date DATETIME NOT NULL
, dir_name VARCHAR(255) NOT NULL
, coverage_percent DECIMAL(5,2) NOT NULL
, PRIMARY KEY (server, version, run_date, dir_name)
) ENGINE=InnoDB;

CREATE TABLE bench_config (
  config_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY
, name VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE bench_runs (
  run_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY
, config_id INT NOT NULL
, server VARCHAR(20) NOT NULL
, version VARCHAR(60) NULL
, run_date DATETIME NOT NULL
) ENGINE=InnoDB;

CREATE TABLE sysbench_run_iterations (
  run_id INT NOT NULL
, concurrency INT NOT NULL
, iteration INT NOT NULL
, tps DECIMAL(13,2) NOT NULL
, read_write_req_per_second DECIMAL(13,2) NOT NULL
, deadlocks_per_second DECIMAL(5,2) NOT NULL
, min_req_latency_ms DECIMAL(10,2) NOT NULL
, avg_req_latency_ms DECIMAL(10,2) NOT NULL
, max_req_latency_ms DECIMAL(10,2) NOT NULL
, 95p_req_latency_ms DECIMAL(10,2) NOT NULL
, PRIMARY KEY (run_id, concurrency, iteration)
) ENGINE=InnoDB;

CREATE TABLE bench_show_status_history (
  run_id INT NOT NULL
, concurrency INT NOT NULL
, variable_name VARCHAR(255) NOT NULL
, value INT NOT NULL
, PRIMARY KEY (run_id, concurrency)
) ENGINE=InnoDB;
  
CREATE TABLE sqlbench_run_iterations (
 run_id INT NOT NULL
, operation_name VARCHAR(40) NOT NULL
, seconds DECIMAL(6,2) NOT NULL
, usr DECIMAL(5,2) NOT NULL
, sys DECIMAL(5,2) NOT NULL
, cpu DECIMAL(5,2) NOT NULL
, tests INT NOT NULL
, engine VARCHAR(20) NOT NULL
, PRIMARY KEY (run_id, operation_name)
) ENGINE=InnoDB;

CREATE TABLE dbt2_run_iterations (
run_id INT NOT NULL
, tpm DECIMAL(6,2) NOT NULL
, connections INT NOT NULL
, test_time INT NOT NULL
, rollbacks INT NOT NULL
, warehouses INT NOT NULL
, PRIMARY KEY (run_id, connections, test_time)
) ENGINE=InnoDB;

CREATE TABLE drizzleslap_run_iterations (
run_id INT NOT NULL
, engine_name VARCHAR(40) NOT NULL
, test_name VARCHAR(40) NOT NULL
, queries_avg DECIMAL(8,3) NOT NULL
, queries_min DECIMAL(8,3) NOT NULL
, queries_max DECIMAL(8,3) NOT NULL
, total_time DECIMAL(8,3) NOT NULL
, stddev DECIMAL(8,3) NOT NULL
, iterations INT NOT NULL
, concurrency INT NOT NULL
, concurrency2 INT NOT NULL
, queries_per_client INT NOT NULL
, PRIMARY KEY (run_id, test_name, concurrency)
) ENGINE=InnoDB;
"""
  execute_sql(create_sql)
