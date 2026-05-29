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

"""Defines the adapter for a simple MySQL client"""

import os
import commands
from drizzle.automation.lib import logging
import sys

"""A class responsible acting as a client to a MySQL server"""
class MySQLClient:

  def __init__(self, basedir, port):
    self._basedir= basedir
    self._port= port

  def execute(self, statement):
    """Executes a supplied SQL statement"""
    client_cmd= "%s --no-defaults --user=root --port=%d --host=127.0.0.1 -e\"%s\"" % (os.path.join(self._basedir, "bin", "mysql")
                                        , self._port
                                        , statement)
    (retcode, output)= commands.getstatusoutput(client_cmd)
    if retcode != 0:
      logging.error("Client on port %d failed to execute SQL:\n\"%s\"\nGot error: %s" % (self._port, statement, output))
      return False
    return True

  def executeFile(self, file):
    """Executes SQL statements in a supplied file"""
    client_cmd= "%s --no-defaults --user=root --port=%d --host=127.0.0.1 < %s" % (os.path.join(self._basedir, "bin", "mysql")
                                        , self._port
                                        , file)
    (retcode, output)= commands.getstatusoutput(client_cmd)
    if retcode != 0:
      logging.error("Client on port %d failed to execute SQL in file:\n\"%s\"\nGot error: %s" % (self._port, file, output))
      return False
    return True

  def fetchAllAssoc(self, statement):
    """Executes a supplied SELECT or SHOW statement and returns a sequence with associative dictionary of results."""
    client_cmd= "%s --no-defaults --user=root --port=%d --host=127.0.0.1 -e\"%s\"" % (os.path.join(self._basedir, "bin", "mysql")
                                        , self._port
                                        , statement)
    (retcode, output)= commands.getstatusoutput(client_cmd)
    if retcode != 0:
      logging.error("Client on port %d failed to execute SQL:\n\"%s\"\nGot error: %s" % (self._port, statement, output))
      return []
    else:
      # Now we build the results dictionary...
      results= []
      # The first line is the field names separated by a tab
      # Every line after is a tab-delimited field values.
      lines= results.split("\n")
      fields= lines[0].split("\t")
      for line in lines[1:]:
        row= {}
        data_fields= line.split("\t")
        fieldno= 0
        for field in fields:
          row[field]= data_fields[fieldno]
          fieldno= fieldno + 1
        results.append(row)
      return results

