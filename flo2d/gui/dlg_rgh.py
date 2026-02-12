# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


import os
from qgis.gui import QgsFileWidget

from .ui_utils import load_ui


uiDialog, qtBaseClass = load_ui("rgh")


class RGHDialog(qtBaseClass, uiDialog):
    """
    Dialog that loads rgh.ui and updates grid.n_value using MANNINGS_N.RGH.
    """

    def __init__(self, con, iface, lyrs, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.con = con
        self.iface = iface
        self.lyrs = lyrs

        # widgets from rgh.ui
        self.gb = self.mannings_n_rgh
        self.fw = self.mannings_n_rgh_path

        # configure file widget
        self.fw.setStorageMode(QgsFileWidget.GetFile)
        self.fw.setFilter("MANNINGS_N.RGH")

        # initial state
        self.gb.setChecked(False)
        self.fw.setEnabled(False)

        # enable/disable file widget based on groupbox checked state
        self.gb.toggled.connect(self.fw.setEnabled)

    def use_rgh(self):
        return self.gb.isChecked()

    def rgh_path(self):
        path = self.fw.filePath()
        if not path:
            return ""

        filename = os.path.basename(path)
        if filename.lower() != "mannings_n.rgh":
            self.uc.bar_warn("Invalid file. The file must be MANNINGS_N.RGH.")
            self.uc.log_info("Invalid file. The file must be MANNINGS_N.RGH.")
            return ""

        return path
