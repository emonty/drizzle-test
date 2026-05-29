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

"""Script to automate SLOCcount reporting."""

import sys
import os
import os.path
import re
from drizzle.automation.lib  import logging
import commands
import datetime

def logSloccountRun(server_name, server_version, run_date, directory, language, count):
  """Stores the results of the run in the database"""
  sql= """
INSERT INTO sloc_stats (server, version, directory, language, run_date, count) VALUES ("%s","%s","%s","%s","%s",%d) ON DUPLICATE KEY UPDATE count= %d, run_date= "%s";
""" % (server_name, server_version, directory, language, run_date, count, count, run_date)
  from drizzle.automation.lib import db
  db.execute_sql(sql)

def execute(processing_mode, variables):
  # Set/verify some required variables, depending on the server
  # we are processing

  working_dir= variables['working_dir']
  run_date= datetime.datetime.now().isoformat()

  # Set of directories we're interested in running coverage reports on
  sloc_dirs= variables['sloc']['directories'].split(',')

  server_name= variables['server']

  # For BZR mode, the "version" of the server (used in identifying the 
  # command run when logging to the database) is the branch and revision number.
  #
  # For MySQL Sandbox mode, the version is the text after the "msb_" prefix
  # on the sandbox.
  if processing_mode == 'bzr':
    server_version= "%s-%s" % (variables['bzr_branch'], variables['bzr_revision'])
  else:
    server_version= variables['mysql_sandbox'].split('_')[1] # Sandbox names are msb_XXXX (e.g. msb_6011 for MySQL 6.0.11)

  os.chdir(working_dir)

  logging.info("Processing SLOC code coverage in \"%s\"." % working_dir)

  tmp_sloc_data_filename= "sloccount.txt"
  cmds= ["sloccount"] + sloc_dirs + ["> %s" % tmp_sloc_data_filename]
  cmd= " ".join(cmds)

  (retcode, output)= commands.getstatusoutput(cmd)

  if not retcode == 0:
    logging.error("Failed to generate SLOC info. Got error: %s" % output)
    sys.exit(1)

  # Step #3: Scrape the SLOC data per directory and language
  logging.info("Scraping SLOC results per directory and language.")

  # Grab our data file for SLOC counts
  sloc_file_lines= open(tmp_sloc_data_filename).readlines()

  # A SLOC line looks like this:
  # 121516  drizzled        cpp=115508,yacc=5416,sh=446,perl=146
  #
  # If the previous line ends in a comma, it means a continuation
  # of the previous directory.  In other words, we got something like this:
  #
  # SLOC	Directory	SLOC-by-Language (Sorted)
  # 149424  plugin          ansic=96226,cpp=50550,python=1388,lex=626,yacc=524,
  #                         sh=110
  # 142968  drizzled        cpp=137726,yacc=5242

  pattern= r"^(\d+)\s+(\S+)\s+(.*)$"
  regex= re.compile(pattern)

  # Scrape the percentages...
  line_counts= {}
  prev_line= None
  prev_dir= None
  for line in sloc_file_lines:

    result= regex.match(line)
    if result:
      count= int(result.group(1)) # groups(0) is the whole match...
      found_dir= result.group(2)
      lang_counts= result.group(3)
      entry= {'count': count, 'lang_counts': {}}

      langs= lang_counts.split(',')
      for keyval in langs:
        (lang, lang_count)= keyval.split('=')
        entry['lang_counts'][lang]= int(lang_count)

      line_counts[found_dir]= entry
      prev_dir= found_dir
    else:
      if prev_line is not None:
        if prev_line[-1] == ",":
          # OK, previous directory has additional langs...
          langs= lang_counts.split(',')
          for keyval in langs:
            (lang, lang_count)= keyval.split('=')
            line_counts[prev_dir]['lang_counts'][lang]= int(lang_count)
          
    prev_line= line

  for dir in sloc_dirs:
    for lang in line_counts[dir]['lang_counts'].keys():
      lang_lines= int(line_counts[dir]['lang_counts'][lang])
      logSloccountRun(server_name, server_version, run_date, dir, lang, lang_lines)

  return True
