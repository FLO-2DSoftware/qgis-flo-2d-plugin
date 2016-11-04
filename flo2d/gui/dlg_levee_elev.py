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
        self.method = None
        self.radio_points_clicked()

        # connections
        self.radio_points.toggled.connect(self.radio_points_clicked)
        self.radio_lines.toggled.connect(self.radio_lines_clicked)
        self.radio_polys.toggled.connect(self.radio_polys_clicked)

    def radio_points_clicked(self):
        self.buffer_size.setEnabled(True)
        if self.buffer_size.value() == 0:
            val = float(self.gutils.get_cont_par('CELLSIZE'))
            self.buffer_size.setValue(val)
        else:
            pass
        self.method = self.elev_from_points

    def radio_lines_clicked(self):
        self.buffer_size.setDisabled(True)
        self.method = self.elev_from_lines

    def radio_polys_clicked(self):
        self.buffer_size.setDisabled(True)
        self.method = self.elev_from_polys

    def elev_from_points(self):
        levee_lines = self.lyrs.get_layer_by_name('Levee Lines', self.lyrs.group).layer()
        levee_points = self.lyrs.get_layer_by_name('Levee Points', self.lyrs.group).layer()
        levee_schematic = self.lyrs.get_layer_by_name('Levees', self.lyrs.group).layer()
        qry = 'UPDATE levee_data SET levcrest = ? WHERE fid = ?;'
        cur = self.con.cursor()
        buf = self.buffer_size.value()
        for feat in levee_lines.getFeatures():
            intervals = get_intervals(feat, levee_points, 'elev', 'correction', buf)
            interpolated = interpolate_along_line(feat, levee_schematic, intervals)
            for row in interpolated:
                cur.execute(qry, row)
        self.con.commit()

    def elev_from_lines(self):
        levee_lines = self.lyrs.get_layer_by_name('Levee Lines', self.lyrs.group).layer()
        qry = 'UPDATE levee_data SET levcrest = ? WHERE user_line_fid = ?;'
        cur = self.con.cursor()
        for feat in levee_lines.getFeatures():
            fid = feat['fid']
            elev = feat['elev']
            cor = feat['correction']
            val = elev + cor if not isinstance(cor, QPyNullVariant) else elev
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
