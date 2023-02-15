# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import time
from subprocess import Popen, PIPE, STDOUT, CREATE_NO_WINDOW, check_call, CalledProcessError, run, call
from contextlib import contextmanager
from ..user_communication import UserCommunication

@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


class FLOPROExecutor(object):

    FLOPRO_EXE = "FLOPRO.exe"

    def __init__(self, iface, flo2d_dir, project_dir):
        self.flo2d_dir = flo2d_dir
        self.flo2d_exe = os.path.join(flo2d_dir, self.FLOPRO_EXE)
        self.project_dir = project_dir
        self.uc = self.uc = UserCommunication(iface, "FLO-2D")

    def execute_flopro(self):
        with cd(self.project_dir):
            #             proc = subprocess.call(self.tailings_exe, shell=True)
            #             proc = Popen(self.tailings_exe, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)

            try:
                   
                #11111:
                # check_call(self.flo2d_exe)
                # result = run(self.flo2d_exe)
                # call(self.flo2d_exe)
                # result = run([self.flo2d_exe],input="",capture_output=True)
                # result = Popen([self.flo2d_exe], shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=PIPE, universal_newlines=False)
                # result = Popen(self.flo2d_exe)    
                # out = result.communicate() 
                # for line in out:
                #     self.uc.bar_info(line)  
                
                #22222
                result = Popen(
                    self.flo2d_exe,
                    shell=True,
                    stdin=open(os.devnull),
                    stdout=PIPE,
                    stderr=STDOUT,
                    universal_newlines=True,
                )
                
                
                
                #33333:
                # result = run([self.flo2d_exe])                  
                
                #44444:
                # result = os.system('"C:\Program Files (x86)\FLO-2D PRO\FLOPRO.EXE"')
                
                
                #55555:
                # (self, args, bufsize=-1, executable=None,
                #  stdin=None, stdout=None, stderr=None,
                #  preexec_fn=None, close_fds=True,
                #  shell=False, cwd=None, env=None, universal_newlines=None,
                #  startupinfo=None, creationflags=0,
                #  restore_signals=True, start_new_session=False,
                #  pass_fds=(), *, encoding=None, errors=None, text=None):
                
                
                self.uc.bar_info("Model started. " ) 
                # result.wait()
                
                return result.returncode 
               
            except Exception as e:
                self.uc.show_error("ERROR 180821.0822: can't run model!/n", e)

    def perform(self):
        return self.execute_flopro()
    
    


class XSECInterpolatorExecutor(object):

    INTERPOLATOR_EXE = "INTERPOLATE.EXE"

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

    CHANRIGHTBANK_EXE = "CHANRIGHTBANK.EXE"

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


class ChannelNInterpolatorExecutor(object):

    N_VALUE_INTERPOLATOR = "CHAN N-VALUE INTERPOLATOR.EXE"

    def __init__(self, channelNinterpolator_dir, project_dir):
        self.channelNinterpolator_dir = channelNinterpolator_dir
        self.channelNinterpolator_exe = os.path.join(channelNinterpolator_dir, self.N_VALUE_INTERPOLATOR)
        self.project_dir = project_dir

    def execute_chanNInterpolator(self):
        if os.path.isfile(os.path.join(self.project_dir, "CHAN.DAT")):
            with cd(self.project_dir):
                proc = Popen(self.channelNinterpolator_exe)
                proc.wait()
                return proc.returncode
        else:
            return -999

    def run(self):
        return self.execute_chanNInterpolator()


class TailingsDamBreachExecutor(object):

    TAILINGS_EXE = "Tailings Dam Breach.exe"

    def __init__(self, tailings_dir, project_dir):
        self.tailings_dir = tailings_dir
        self.tailings_exe = os.path.join(tailings_dir, self.TAILINGS_EXE)
        self.project_dir = project_dir

    def execute_tailings(self):
        with cd(self.project_dir):
            proc = Popen(
                self.tailings_exe,
                shell=True,
                stdin=open(os.devnull),
                stdout=PIPE,
                stderr=STDOUT,
                universal_newlines=True,
            )
            return proc.returncode

    def perform(self):
        return self.execute_tailings()


class MapperExecutor(object):

    MAPPER_EXE = "Mapper PRO.exe"

    def __init__(self, mapper_dir, project_dir):
        self.mapper_dir = mapper_dir
        self.mapper_exe = os.path.join(mapper_dir, self.MAPPER_EXE)
        self.project_dir = project_dir

    def execute_mapper(self):
        with cd(self.project_dir):
            Popen(self.mapper_exe)

    def perform(self):
        return self.execute_mapper()


class ProgramExecutor(object):
    def __init__(self, exe_dir, project_dir, exe_name):
        self.exe = os.path.join(exe_dir, exe_name)
        self.project_dir = project_dir

    def execute_exe(self):
        with cd(self.project_dir):
            Popen(self.exe)

    def perform(self):
        return self.execute_exe()
