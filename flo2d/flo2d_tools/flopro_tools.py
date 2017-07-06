# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from subprocess import Popen
from contextlib import contextmanager


@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


class FLOPROExecutor(object):

    FLOPRO_EXE = 'FLOPRO.exe'

    def __init__(self, flo2d_dir, project_dir):
        self.flo2d_dir = flo2d_dir
        self.flo2d_exe = os.path.join(flo2d_dir, self.FLOPRO_EXE)
        self.project_dir = project_dir

    def execute_flopro(self):
        with cd(self.project_dir):
            Popen(self.flo2d_exe)

    def run(self):
        self.execute_flopro()
