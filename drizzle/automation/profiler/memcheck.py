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

"""Defines the adapter for Valgrind's memory checker profiler tool"""

import os
import commands
from drizzle.automation.lib  import logging
import sys
import time

"""A class which wraps memory checking around a server"""
class MemcheckProfiler:

  def __init__(self, log_file):
    self._log_file= log_file

  def getStartCmdPrefix(self): 
    """Returns command to go in front of a server's start command"""
    return "libtool --mode=execute valgrind --log-file=%s --leak-check=full" % self._log_file
