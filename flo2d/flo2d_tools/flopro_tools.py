# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import os
import time
import warnings
from contextlib import contextmanager
from subprocess import (
    CREATE_NO_WINDOW,
    PIPE,
    STDOUT,
    CalledProcessError,
    Popen,
    call,
    check_call,
    check_output,
    run,
)

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

    def __init__(self, iface, flo2d_dir, project_dir, program):
        self.program = program
        self.flo2d_dir = flo2d_dir
        self.flo2d_exe = flo2d_dir + "/" + self.program
        # self.flo2d_exe = os.path.join(flo2d_dir, self.FLOPRO_EXE)
        self.project_dir = project_dir
        self.uc = self.uc = UserCommunication(iface, "FLO-2D")

    def execute_flopro(self):
        with cd(self.project_dir):
            try:
                self.uc.clear_bar_messages()

                # 11111:
                # check_call(self.flo2d_exe)
                # result = run(self.flo2d_exe)
                # call(self.flo2d_exe)
                # result = run([self.flo2d_exe],input="",capture_output=True)
                # result = Popen([self.flo2d_exe], shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=PIPE, universal_newlines=False)

                # 00000
                # result = Popen(self.flo2d_exe)
                # out = result.communicate()
                # for line in out:
                #     self.uc.bar_info(line)

                # result = run(["self.flo2d_exe"], shell=True, capture_output=True, text=True)

                # 22222

                # self.flo2d_exe = "C:/TRACKS/FLOPROCore/FLOPROCore/bin/Debug/net6.0-windows/FLOPROCore.exe"

                with open(os.devnull, 'r') as devnull:
                    result = Popen(
                        args=self.flo2d_exe,
                        shell=False,
                        stdin=devnull,
                        stdout=PIPE,
                        stderr=STDOUT
                    )
                    output, _ = result.communicate()

                # result = Popen(
                #     args=self.flo2d_exe,
                #     bufsize=-1,
                #     executable=None,
                #     stdin=None,
                #     stdout=None,
                #     stderr=None,
                #     preexec_fn=None,
                #     close_fds=True,
                #     shell=False,
                #     cwd=None,
                #     env=None,
                #     universal_newlines=None,
                #     startupinfo=None,
                #     creationflags=0,
                #     restore_signals=True,
                #     start_new_session=False,
                #     pass_fds=(),
                #     group=None,
                #     extra_groups=None,
                #     user=None,
                #     umask=-1,
                #     encoding=None,
                #     errors=None,
                #     text=None,
                # )
                # out = result.communicate()
                # for line in out:
                #     self.uc.bar_info(line)

                # check_output(self.flo2d_exe, shell=True)

                # 33333:
                # result = run([self.flo2d_exe])

                # 44444:
                # result = os.system(self.flo2d_exe)

                # 555555
                # result = call(self.flo2d_exe)

                self.uc.bar_info(
                    f"Model {self.program} started " + str(result) if result is not None else "",
                    10,
                )

                return result

            except Exception as e:
                self.uc.show_error("ERROR 180821.0822: can't run model!\n", e)

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
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                Popen(self.exe)

    def perform(self):
        return self.execute_exe()
