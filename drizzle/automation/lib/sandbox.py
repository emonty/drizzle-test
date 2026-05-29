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

"""Module responsible for creating a sandbox for a run configuration

A sandbox is simply a directory where a specific run configuration can
be built and processed without interfering with another run or run failure.

The sandbox directory structure is setup like so:

  First, we grab the branch-dir from the command's configuration or 
  overriding CLI option.  This is the directory where the *parent* bzr 
  branch is located.

  We then create a new branch in our repository for this specific 
  combination of $command/$branch/$revno.
"""

from drizzle.automation.lib  import logging
import os
import sys
import commands

class RootSandbox:

  def __init__(self, repo_dir, branch):
    self.repo_dir= repo_dir
    # The nickname or common name for the branch this sandbox tests, e.g "lp:drizzle"
    self.branch= branch
    self.branch_nick= branch
    self.branch_dir= branch
    self.is_lp_branch= False
    if branch[:3] == "lp:":
      self.is_lp_branch= True
      self.branch_nick= branch[3:].split('/')[-1]
      self.branch_dir= branch[3:].replace('/','_').replace('~','_').replace('+','_').replace(':','_')

  def create(self,no_pull_flag, use_root_sandbox ):
    """Creates the sandbox for the tip of the branch"""
    if os.path.exists(self.repo_dir) and not os.path.isdir(self.repo_dir):
      logging.error("Repo dir doesn't exist and there is something in the way")
      sys.exit(1)

    if not os.path.isdir(self.repo_dir):
      os.system("bzr init-repo %s" % self.repo_dir)

    os.chdir(self.repo_dir)

    if use_root_sandbox is False:
      if not os.path.isdir(self.branch_dir):
        if self.is_lp_branch:
          os.system("bzr branch %s %s" % (self.branch, self.branch_dir))
        else:
          logging.error("%s branch doesn't exist, but you didn't tell me where to grab it from" % (self.branch))
          sys.exit(1)

      test_root_branch_dir= os.path.join(self.repo_dir, self.branch_dir)

      os.chdir(test_root_branch_dir)

    if no_pull_flag is False:
      logging.info("Pulling latest revision into sandbox root \"%s\" with \"bzr pull --overwrite\"" % test_root_branch_dir)

      (retcode, output)= commands.getstatusoutput("bzr pull --overwrite")
      if retcode != 0:
        (retcode2, revno)= commands.getstatusoutput("bzr revno")
        logging.error("Branch directory \"%s\" in repo-dir \"%s\" exists, but is not a BZR branch! bzr revision = %s,  Error code = %d" % (test_root_branch_dir, self.repo_dir,revno,retcode))
        sys.exit(1)
    (retcode, output)= commands.getstatusoutput("bzr revno")
    self.revno= output

  def get_revision_range(self, revision_string, step= 1):
    """Returns a sequence of revision number if the revision option was specified as a range"""

    # Replace the word "HEAD" in the revision string with the latest
    # revno for the specified branch-dir
    revision_string= str(revision_string)
    revision_string= revision_string.lower().replace("last:1", self.revno)
    revision_string= revision_string.lower().replace("HEAD", self.revno)
    results= []
    l_revision= str(revision_string)
    if l_revision.find("..") != -1:
      (range_start, range_end)= [int(x) for x in l_revision.split("..")]
      results= range(range_start, range_end + 1, step)
    else:
      results= [revision_string]
    return results


class Sandbox:

  def __init__(self, command, repo_root, revno):
    # The automation command this sandbox will be used for
    self.command= command
    # The root repository from which to look for branches
    self.repo_root= repo_root
    # The revision of the branch which this sandbox tests
    self.revno= revno
    # The location of the branch for this sandbox
    self.branch_dir= os.path.join(self.repo_root.repo_dir, '-'.join([self.repo_root.branch_dir,self.command]))
    self.revisional_branch_dir= '-'.join([self.branch_dir,self.command,'r' + str(self.revno)])

  def create(self):
    """Creates the sandbox if not already created."""

    if os.path.exists(self.branch_dir):
      if not os.path.isdir(self.branch_dir):
        logging.error("Specified branch \"%s\" in repo-dir \"%s\" exists, but is not a directory! Exiting." % (self.branch_dir, self.repo_root.repo_dir))
        sys.exit(1)

      # OK, we have a directory already for the branch.
      # Check to see if it's a bzr branch.
      os.chdir(self.branch_dir)

      logging.info("Pulling latest revision into sandbox parent \"%s\"" % self.branch_dir)
      
      (retcode, output)= commands.getstatusoutput("bzr pull --overwrite")
      if retcode != 0:
        logging.error("Branch directory \"%s\" in repo-dir \"%s\" exists, but is not a BZR branch! Error code = %d." % (self.branch_dir, self.repo_root.repo_dir,retcode))
        sys.exit(1)

      (retcode, output)= commands.getstatusoutput("bzr revno")

      logging.info("Parent sandbox found in \"%s\" at revision %s" % (self.branch_dir, output))


      if os.path.exists(self.revisional_branch_dir):
        if not os.path.isdir(self.revisional_branch_dir):
          logging.error("Sandbox branch \"%s\" exists, but is not a directory! Exiting." % self.revisional_branch_dir)
          sys.exit(1)

        # OK, we have a directory already for the revisional (sandbox) branch.
        # Check to see if it's a bzr branch.
        os.chdir(self.revisional_branch_dir)

        (retcode, output)= commands.getstatusoutput("bzr pull -r%s --overwrite" % self.revno)
        if retcode != 0:
          logging.error("Sandbox directory \"%s\" exists, but is not a BZR branch! Exiting." % (self.revisional_branch_dir))
          sys.exit(1)

        (retcode, output)= commands.getstatusoutput("bzr revno")

        logging.info("Existing sandbox found in \"%s\" at revision %s" % (self.revisional_branch_dir, output))

      else:
        # OK, found our command branch.  Now create our sandbox
        # branch at the specific revision needed.
        branch_cmd= "bzr branch -r%s %s %s" % (self.revno, self.branch_dir, self.revisional_branch_dir)

        logging.info("Creating sandbox at %s" % self.revisional_branch_dir)
        (retcode, output)= commands.getstatusoutput(branch_cmd)
        if retcode != 0:
          logging.error("Failed to create sandbox branch \"%s\"! Exiting." % self.revisional_branch_dir)
          sys.exit(1)

    else:
      # OK, no directory exists for /repo-dir/$branch-$command.  Check to see if 
      # even /repo-dir/$branch exists...

      test_parent_dir= os.path.join(self.repo_root.repo_dir, self.repo_root.branch_dir)
      if os.path.exists(test_parent_dir):
        if not os.path.isdir(test_parent_dir):
          logging.error("Found a logical parent \"%s\" under the repository, but is not a directory! Exiting." % test_parent_dir)
          sys.exit(1)

        # OK, at least we have a parent directory. Test to see if it's
        # a BZR branch we can work with...
        os.chdir(test_parent_dir)

        (retcode, output)= commands.getstatusoutput("bzr revno")
        if retcode != 0:
          logging.error("The logical parent directory \"%s\" exists, but is not a BZR branch! Exiting." % test_parent_dir)
          sys.exit(1)

        # OK, our logical parent is a BZR branch. Create the
        # command branch now.
        branch_cmd= "bzr branch %s %s" % (test_parent_dir, self.branch_dir)

        logging.info("Creating sandbox's command branch at %s" % self.branch_dir)

        (retcode, output)= commands.getstatusoutput(branch_cmd)
        if retcode != 0:
          logging.error("Failed to create the command branch \"%s\" under our logical parent directory \"%s\"! Exiting." % (self.branch_dir, test_parent_dir))
          sys.exit(1)

        # OK, created our command branch.  Now create our sandbox
        # branch at the specific revision needed.
        branch_cmd= "bzr branch -r%s %s %s" % (self.revno, self.branch_dir, self.revisional_branch_dir)

        logging.info("Creating sandbox at %s" % self.revisional_branch_dir)

        (retcode, output)= commands.getstatusoutput(branch_cmd)
        if retcode != 0:
          logging.error("Failed to create sandbox branch \"%s\"! Exiting." % self.revisional_branch_dir)
          sys.exit(1)

      else:
        # There was no directory at /repo-dir/$branch :(
        logging.error("""Could not find a BZR branch at \"%s\".
You must first create the root branch from which drizzle-automation will pull. Exiting.""" % test_parent_dir)
        sys.exit(1)

  def get_working_dir(self):
    """Returns the full path to the sandbox's working directory"""
    return self.revisional_branch_dir

  def setup(self):
    """Run before the automation process enters the sandbox."""
    pass

  def teardown(self):
    """Run after the automation process enters the sandbox."""
    pass
