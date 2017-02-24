# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from ..elevation_correctors import LeveesElevation
from ..geopackage_utils import GeoPackageUtils
from .utils import load_ui

uiDialog, qtBaseClass = load_ui('levees_elevation')


class LeveesToolDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.iface = iface
        self.setupUi(self)
        self.con = con
        self.lyrs = lyrs
        self.gutils = GeoPackageUtils(con, iface)
        self.corrector = LeveesElevation(self.gutils, self.lyrs)
        self.corrector.setup_layers()
        self.methods = {}

        # connections
        self.elev_polygons_chbox.stateChanged.connect(self.polygons_checked)
        self.elev_points_chbox.stateChanged.connect(self.points_checked)
        self.elev_lines_chbox.stateChanged.connect(self.lines_checked)

        self.elev_polygons_chbox.setChecked(True)
        self.elev_points_chbox.setChecked(True)
        self.elev_lines_chbox.setChecked(True)

    def points_checked(self):
        if self.elev_points_chbox.isChecked():
            self.buffer_size.setEnabled(True)
            if self.buffer_size.value() == 0:
                val = float(self.gutils.get_cont_par('CELLSIZE'))
                self.buffer_size.setValue(val)
            else:
                pass
            self.methods[2] = self.elev_from_points
        else:
            self.buffer_size.setDisabled(True)
            self.methods.pop(2)

    def lines_checked(self):
        if self.elev_lines_chbox.isChecked():
            self.methods[1] = self.elev_from_lines
        else:
            self.methods.pop(1)

    def polygons_checked(self):
        if self.elev_polygons_chbox.isChecked():
            self.methods[3] = self.elev_from_polys
        else:
            self.methods.pop(3)

    def elev_from_points(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_points(self.buffer_size.value())
        finally:
            self.corrector.clear_filter()

    def elev_from_lines(self):
        self.corrector.elevation_from_lines()

    def elev_from_polys(self):
        try:
            self.corrector.set_filter()
            self.corrector.elevation_from_polygons()
        finally:
            self.corrector.clear_filter()
