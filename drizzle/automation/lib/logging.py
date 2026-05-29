#! /usr/bin/python
# -*- mode: python; c-basic-offset: 2; indent-tabs-mode: nil; -*-
# vim:expandtab:shiftwidth=2:tabstop=2:smarttab:
#
# Copyright (C) 2009 Sun Microsystems
#
# Authors:
#
#  Jay Pipes <joinfu@sun.com>
#  Monty Taylor <mordred@sun.com>
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

""" Simple replacement for python logging module that doesn't suck """

import time, sys

log_file=sys.stdout

def _write_message(level, msg):
  global log_file
  log_file.write("%s %s: %s\n" % (time.asctime(), level, str(msg)))
  log_file.flush()

def setOutput(file_name):
  global log_file
  if file_name == 'stdout':
    log_file= sys.stdout
  else:
    log_file= open(variables['log_file'],'w+')

def info(msg):
  _write_message("INFO", msg)

def warning(msg):
  _write_message("WARNING", msg)

def error(msg):
  _write_message("ERROR", msg)
