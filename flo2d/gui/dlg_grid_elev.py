# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from flo2d.flo2d_tools.elevation_correctors import GridElevation
from ui_utils import load_ui
from flo2d.geopackage_utils import GeoPackageUtils

uiDialog, qtBaseClass = load_ui('grid_elevation')


class GridCorrectionDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.gutils = GeoPackageUtils(con, iface)
        self.corrector = GridElevation(self.gutils, self.lyrs)
        self.corrector.setup_layers()

        self.methods = {}

        # connections
        self.elev_tin_chbox.stateChanged.connect(self.tin_checked)
        self.elev_polygons_chbox.stateChanged.connect(self.polygons_checked)
        self.elev_arf_chbox.stateChanged.connect(self.arf_checked)

    def tin_checked(self):
        if self.elev_tin_chbox.isChecked():
            self.methods[1] = self.tin_method
        else:
            self.methods.pop(1)

    def polygons_checked(self):
        if self.elev_polygons_chbox.isChecked():
            self.methods[2] = self.polygon_method
        else:
            self.methods.pop(2)

    def arf_checked(self):
        if self.elev_arf_chbox.isChecked():
            self.stats_cbx.setEnabled(True)
            self.methods[3] = self.arf_method
        else:
            self.methods.pop(3)
            self.stats_cbx.setDisabled(True)

    def tin_method(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_tin()
        finally:
            self.corrector.clear_filter()

    def polygon_method(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_polygons()
        finally:
            self.corrector.clear_filter()

    def arf_method(self):
        self.corrector.elevation_within_arf(self.stats_cbx.currentText())
