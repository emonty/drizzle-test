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

"""Processes configuration for automation scripts"""

import sys
import os
import ConfigParser
from drizzle.automation.lib  import logging


"""
Processes the configuration file for the supplied command and 
returns a dictionary with relevant configuration options for 
the command.
"""
def process_config(variables):
  command= variables['command']
  # Look for a configuration file for the supplied command
  # We look in order:
  #   $cwd/[command].cnf
  #   ~/[command].cnf
  #   /etc/drizzle-automation/[command].cnf
  #   /etc/drizzle-automation/automation.cnf
  #
  # The order in locations[] is reversed because we read the
  # files in reverse to the options are overridden with more
  # local configuration files
  locations= [
    os.path.join("/etc", "drizzle-automation", "automation.cnf") # The shared config file for all automation commands
  , os.path.join("/etc", "drizzle-automation", "%s.cnf" % command.lower())
  , os.path.expanduser(os.path.join("~", ".drizzle-automation", "automation.cnf"))
  , os.path.expanduser(os.path.join("~", ".drizzle-automation", "%s.cnf" % command.lower()))
  , os.path.join(os.getcwd(), "%s.cnf" % command.lower())
  ]
  parser= ConfigParser.RawConfigParser()
  read_files= parser.read(locations)
  for sec in parser.sections():
    variables[sec]= {}
    for k,v in parser.items(sec):
      variables[sec][k]= v
  return variables
