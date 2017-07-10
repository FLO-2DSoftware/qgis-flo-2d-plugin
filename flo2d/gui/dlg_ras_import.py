# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
from flo2d.flo2d_ie.ras_io import RASProject
from ui_utils import load_ui
from flo2d.user_communication import UserCommunication
from PyQt4.QtCore import QSettings
from PyQt4.QtGui import QFileDialog

uiDialog, qtBaseClass = load_ui('ras_import')


class RasImportDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, parent=None):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.setupUi(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.uc = UserCommunication(iface, 'FLO-2D')

        self.browse_btn.clicked.connect(self.get_ras_file)

    def get_ras_file(self):
        s = QSettings()
        last_dir = s.value('FLO-2D/lastRasDir', '')
        ras_file = QFileDialog.getOpenFileName(
            None,
            'Select HEC-RAS project or geometry file to import data',
            directory=last_dir,
            filter='(*.prj *.g*)')
        if not ras_file:
            return
        self.ras_line.setText(ras_file)
        s.setValue('FLO-2D/lastRasDir', os.path.dirname(ras_file))

    def import_geometry(self):
        ras_file = self.ras_line.text()
        interpolated_xs = True if self.interpolated.isChecked() else False
        if ras_file.lower().endswith('.prj'):
            project = RASProject(self.con, self.iface, self.lyrs, prj_path=ras_file, interpolated=interpolated_xs)
            project.find_geometry()
            ras_geom = project.get_geometry()
        else:
            project = RASProject(self.con, self.iface, self.lyrs, interpolated=interpolated_xs)
            ras_geom = project.get_geometry(ras_file)
        if self.bank_radio.isChecked():
            limit = 1
        elif self.levee_radio.isChecked():
            limit = 2
        else:
            limit = 0
        project.write_xsections(ras_geom, limit)
