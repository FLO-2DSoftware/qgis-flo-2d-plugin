# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import QPyNullVariant
from ..schematic_tools import get_intervals, interpolate_along_line, polys2levees
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
        levee_lines = self.lyrs.get_layer_by_name('Levee Lines', self.lyrs.group).layer()
        levee_points = self.lyrs.get_layer_by_name('Levee Points', self.lyrs.group).layer()
        levee_schematic = self.lyrs.get_layer_by_name('Levees', self.lyrs.group).layer()
        qry = 'UPDATE levee_data SET levcrest = ? WHERE fid = ?;'
        cur = self.con.cursor()
        buf = self.buffer_size.value()
        for feat in levee_lines.getFeatures():
            intervals = get_intervals(feat, levee_points, 'elev', buf)
            interpolated = interpolate_along_line(feat, levee_schematic, intervals)
            for row in interpolated:
                cur.execute(qry, row)
        self.con.commit()

    def elev_from_lines(self):
        levee_lines = self.lyrs.get_layer_by_name('Levee Lines', self.lyrs.group).layer()
        cur = self.con.cursor()
        for feat in levee_lines.getFeatures():
            fid = feat['fid']
            elev = feat['elev']
            cor = feat['correction']
            qry = 'UPDATE levee_data SET levcrest = ? WHERE user_line_fid = ?;'
            if not isinstance(elev, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
                val = elev + cor
            elif not isinstance(elev, QPyNullVariant) and isinstance(cor, QPyNullVariant):
                val = elev
            elif isinstance(elev, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
                qry = 'UPDATE levee_data SET levcrest = levcrest + ? WHERE user_line_fid = ?;'
                val = cor
            else:
                continue
            cur.execute(qry, (val, fid))
        self.con.commit()

    def elev_from_polys(self):
        levee_lines = self.lyrs.get_layer_by_name('Levee Lines', self.lyrs.group).layer()
        levee_polys = self.lyrs.get_layer_by_name('Levee Polygons', self.lyrs.group).layer()
        levee_schematic = self.lyrs.get_layer_by_name('Levees', self.lyrs.group).layer()
        qry = 'UPDATE levee_data SET levcrest = ? WHERE fid = ?;'
        cur = self.con.cursor()
        for feat in levee_lines.getFeatures():
            poly_values = polys2levees(feat, levee_polys, levee_schematic, 'elev', 'correction')
            for row in poly_values:
                cur.execute(qry, row)
        self.con.commit()
