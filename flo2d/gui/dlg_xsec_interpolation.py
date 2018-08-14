# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from ui_utils import load_ui
from flo2d.user_communication import UserCommunication
from PyQt4.QtCore import QSettings
from PyQt4.QtGui import QFileDialog, QDialogButtonBox

uiDialog, qtBaseClass = load_ui('interpolate_xsections')


class XSecInterpolationDialog(qtBaseClass, uiDialog):

    def __init__(self, iface,  xs_survey, parent=None,):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self, parent)
        self.setupUi(self)
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.interpolation_browse.clicked.connect(self.get_interpolation_dir)
        self.project_browse.clicked.connect(self.get_project_dir)
        self.set_previous_paths()
        self.surveyed_lbl.setText(str(xs_survey[0]))
        self.non_surveyed_lbl.setText(str(xs_survey[1]))
        self.buttonBox.button(QDialogButtonBox.Ok).setText("Interpolate")
        s = QSettings()
        outdir =  s.value('FLO-2D/lastGdsDir', '')
        self.directory_lbl.setText("(directory: " + outdir + ")")

    def set_previous_paths(self):
        s = QSettings()
        interpolation_dir = s.value('FLO-2D/last_flopro', '')
#         interpolation_dir = s.value('FLO-2D/last_interpolation', '')
        project_dir = s.value('FLO-2D/lastGdsDir', '')
        self.interpolation_le.setText(interpolation_dir)
        self.project_le.setText(project_dir)

    def get_interpolation_dir(self):
        s = QSettings()
        interpolation_dir = QFileDialog.getExistingDirectory(
            None,
            'Select Cross Sections Interpolation program folder',
            directory=self.interpolation_le.text())
        if not interpolation_dir:
            return
        self.interpolation_le.setText(interpolation_dir)
        s.setValue('FLO-2D/last_interpolation', interpolation_dir)

    def get_project_dir(self):
        s = QSettings()
        project_dir = QFileDialog.getExistingDirectory(
            None,
            'Select FLO-2D project folder',
            directory=self.project_le.text())
        if not project_dir:
            return
        self.project_le.setText(project_dir)
        s.setValue('FLO-2D/lastGdsDir', project_dir)

    def get_parameters(self):
        return self.interpolation_le.text(), self.project_le.text()
