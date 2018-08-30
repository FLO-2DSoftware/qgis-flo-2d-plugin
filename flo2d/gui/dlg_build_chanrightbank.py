# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2017 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from .ui_utils import load_ui
from ..user_communication import UserCommunication
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog

uiDialog, qtBaseClass = load_ui('build_chanrightbank')


class BuildChanRightBankDialog(qtBaseClass, uiDialog):

    def __init__(self, iface):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.iface = iface
        self.uc = UserCommunication(iface, 'FLO-2D')
        self.chanrightbank_browse.clicked.connect(self.get_chanrightbank_dir)
        self.project_browse.clicked.connect(self.get_project_dir)
        self.set_previous_paths()

    def set_previous_paths(self):
        s = QSettings()
        chanrightbank_dir = s.value('FLO-2D/last_chanrightbank', '')
        project_dir = s.value('FLO-2D/last_flopro_project', '')
        self.chanrightbank_le.setText(chanrightbank_dir)
        self.project_le.setText(project_dir)

    def get_chanrightbank_dir(self):
        s = QSettings()
        chanrightbank_dir = QFileDialog.getExistingDirectory(
            None,
            'Select CHANRIGHTBANK.EXE program folder',
            directory=self.chanrightbank_le.text())
        if not chanrightbank_dir:
            return
        self.chanrightbank_le.setText(chanrightbank_dir)
        s.setValue('FLO-2D/last_chanrightbank', chanrightbank_dir)

    def get_project_dir(self):
        s = QSettings()
        project_dir = QFileDialog.getExistingDirectory(
            None,
            'Select FLO-2D project folder',
            directory=self.project_le.text())
        if not project_dir:
            return
        self.project_le.setText(project_dir)
        s.setValue('FLO-2D/last_flopro_project', project_dir)

    def get_parameters(self):
        return self.chanrightbank_le.text(), self.project_le.text()
