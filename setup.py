#! /usr/bin/python
# -*- mode: c; c-basic-offset: 2; indent-tabs-mode: nil; -*-
# vim:expandtab:shiftwidth=2:tabstop=2:smarttab:
#
# Copyright (C) 2009 Sun Microsystems
#
# Authors:
#
#  Jay Pipes <joinfu@sun.com>
#  Monty Taylor <mordred@inaugust.com>
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

from ez_setup import use_setuptools
use_setuptools()

from setuptools import setup

description= "Development and testing automation for Drizzle"
classifiers="""\
    Development Status :: 3 - Alpha
    Intended Audience :: Developers
    License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)
    Operating System :: POSIX :: Linux
    Operating System :: POSIX :: SunOS/Solaris
    Operating System :: MacOS :: MacOS X
    Programming Language :: Python
    Topic :: Database
    Topic :: Database :: Front-Ends"""


setup(name= "drizzle-automation",
      version= "1.0.1",
      description= description,
      long_description=description,
      author= "Jay Pipes",
      author_email= "joinfu@sun.com",
      license= "LGPL",
      platforms="linux",
      classifiers=filter(None, classifiers.splitlines()),
      url= "http://launchpad.net/drizzle-automation",

      packages= [
        "drizzle",
        "drizzle.automation",
        "drizzle.automation.builder",
        "drizzle.automation.client",
        "drizzle.automation.crashme",
        "drizzle.automation.dbt2",
        "drizzle.automation.drizzleslap",
        "drizzle.automation.doxy",
        "drizzle.automation.lcov",
        "drizzle.automation.lib",
        "drizzle.automation.profiler",
        "drizzle.automation.randgen",
        "drizzle.automation.reports",
        "drizzle.automation.server",
        "drizzle.automation.sloc",
        "drizzle.automation.sqlbench",
        "drizzle.automation.sysbench"
      ],
      entry_points= {
        'console_scripts': [
          'drizzle-automation = drizzle.automation.runner:run',
          'darts = drizzle.automation.runner:run',
        ]
      },
)
