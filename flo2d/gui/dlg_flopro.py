# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from .ui_utils import load_ui
from ..user_communication import UserCommunication
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog, QApplication
from ..flo2d_tools.flopro_tools import FLOPROExecutor

uiDialog, qtBaseClass = load_ui("flopro")


class ExternalProgramFLO2D(qtBaseClass, uiDialog):
    def __init__(self, iface, title):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.iface = iface
        self.uc = UserCommunication(iface, "FLO-2D")
        self.flo2d_browse.clicked.connect(self.get_flo2d_dir)
        self.project_browse.clicked.connect(self.get_project_dir)
        self.debug_run_btn.clicked.connect(self.debug_run)
        self.set_previous_paths(title)

    def set_previous_paths(self, title):
        self.setWindowTitle(title)
        s = QSettings()
        flo2d_dir = s.value("FLO-2D/last_flopro", "")
        project_dir = last_dir = s.value("FLO-2D/lastGdsDir", "")
        self.flo2d_le.setText(flo2d_dir)
        self.project_le.setText(project_dir)

    #         s.setValue('FLO-2D/last_flopro', flo2d_dir)
    #         s.setValue('FLO-2D/last_flopro_project', project_dir)

    def get_flo2d_dir(self):
        s = QSettings()
        flo2d_dir = QFileDialog.getExistingDirectory(
            None, "Select FLO-2D program folder", directory=self.flo2d_le.text()
        )
        if not flo2d_dir:
            return
        self.flo2d_le.setText(flo2d_dir)
        s.setValue("FLO-2D/last_flopro", flo2d_dir)

    def get_project_dir(self):
        s = QSettings()
        project_dir = QFileDialog.getExistingDirectory(
            None, "Select FLO-2D project folder", directory=self.project_le.text()
        )
        if not project_dir:
            return
        self.project_le.setText(project_dir)
        s.setValue("FLO-2D/lastGdsDir", project_dir)

    def get_parameters(self):
        return self.flo2d_le.text(), self.project_le.text()

    def debug_run(self):
        try:
            self.uc.show_info("Run 0.4 min debug")
            s = QSettings()
            flo2d_dir = self.flo2d_le.text()
            project_dir = self.project_le.text()
            debugDAT = os.path.join(project_dir, "QGISDEBUG.DAT")
            with open(debugDAT, "w") as f:
                f.write("")

            simulation = FLOPROExecutor(flo2d_dir, project_dir)
            simulation.run()
            self.uc.bar_info("Debug simulation started!", dur=3)

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.uc.show_error("ERROR 250419.1729: can't run debug model!.\n", e)
