# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from ..elevation_correctors import GridElevation
from ..geopackage_utils import GeoPackageUtils
from .utils import load_ui

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
        self.elev_polygons_chbox.stateChanged.connect(self.polygons_checked)
        self.elev_tin_chbox.stateChanged.connect(self.tin_checked)

        self.elev_polygons_chbox.setChecked(True)
        self.elev_tin_chbox.setChecked(True)

    def polygons_checked(self):
        if self.elev_polygons_chbox.isChecked():
            self.methods[2] = self.polygon_method
        else:
            self.methods.pop(2)

    def tin_checked(self):
        if self.elev_tin_chbox.isChecked():
            self.methods[1] = self.tin_method
        else:
            self.methods.pop(1)

    def polygon_method(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_polygons()
        finally:
            self.corrector.clear_filter()

    def tin_method(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_tin()
        finally:
            self.corrector.clear_filter()
