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


class XSECInterpolatorExecutor(object):

    INTERPOLATOR_EXE = 'INTERPOLATE.EXE'

    def __init__(self, interpolator_dir, project_dir):
        self.interpolator_dir = interpolator_dir
        self.interpolator_exe = os.path.join(interpolator_dir, self.INTERPOLATOR_EXE)
        self.project_dir = project_dir

    def execute_interpolator(self):
        with cd(self.project_dir):
            proc = Popen(self.interpolator_exe)
            proc.wait()
            return proc.returncode

    def run(self):
        return self.execute_interpolator()


class ChanRightBankExecutor(object):

    CHANRIGHTBANK_EXE = 'CHANRIGHTBANK.EXE'

    def __init__(self, chanrightbank_dir, project_dir):
        self.chanrightbank_dir = chanrightbank_dir
        self.chanrightbank_exe = os.path.join(chanrightbank_dir, self.CHANRIGHTBANK_EXE)
        self.project_dir = project_dir

    def execute_chanrightbank(self):
        with cd(self.project_dir):
            proc = Popen(self.chanrightbank_exe)
            proc.wait()
            return proc.returncode

    def run(self):
        return self.execute_chanrightbank()
