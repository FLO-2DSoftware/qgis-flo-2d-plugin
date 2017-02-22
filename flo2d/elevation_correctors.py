# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from grid_tools import TINInterpolator, poly2grid
from schematic_tools import get_intervals, interpolate_along_line, polys2levees
from qgis.core import QgsFeatureRequest
from PyQt4.QtCore import QPyNullVariant


class ElevationCorrector(object):

    ELEVATION_FIELD = 'elev'
    CORRECTION_FIELD = 'correction'

    def __init__(self, gutils, lyrs):
        self.gutils = gutils
        self.lyrs = lyrs
        self.points = None
        self.lines = None
        self.polygons = None
        self.tin = None
        self.schematic = None
        self.filter_expression = ''

    def set_filter(self):
        self.points.setSubsetString(self.filter_expression.format('user_elevation_points'))
        self.polygons.setSubsetString(self.filter_expression.format('user_elevation_polygons'))

    def clear_filter(self):
        self.points.setSubsetString('')
        self.polygons.setSubsetString('')


class GridElevation(ElevationCorrector):

    def __init__(self, gutils, lyrs):
        super(GridElevation, self).__init__(gutils, lyrs)

    def setup_layers(self):
        self.points = self.lyrs.data['user_elevation_points']['qlyr']
        self.polygons = self.lyrs.data['user_elevation_polygons']['qlyr']
        self.schematic = self.lyrs.data['grid']['qlyr']
        self.filter_expression = "SELECT * FROM {} WHERE membership = 'all' OR membership = 'grid';"

    def elevation_from_polygons(self):
        set_qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
        add_qry = 'UPDATE grid SET elevation = elevation + ? WHERE fid = ?;'
        set_add_qry = 'UPDATE grid SET elevation = ? + ? WHERE fid = ?;'
        cur = self.gutils.con.cursor()
        for el, cor, fid in poly2grid(self.schematic, self.polygons, None, self.ELEVATION_FIELD, self.CORRECTION_FIELD):
            if not isinstance(el, QPyNullVariant) and isinstance(cor, QPyNullVariant):
                cur.execute(set_qry, (el, fid))
            elif isinstance(el, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
                cur.execute(add_qry, (cor, fid))
            elif not isinstance(el, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
                cur.execute(set_add_qry, (el, cor, fid))
            else:
                pass
        self.gutils.con.commit()

    def elevation_from_tin(self):
        qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
        self.tin = TINInterpolator(self.points, self.ELEVATION_FIELD)
        self.tin.setup_layer_data()
        grid_fids = [val[0] for val in poly2grid(self.schematic, self.polygons, None)]
        cur = self.gutils.con.cursor()
        request = QgsFeatureRequest().setFilterFids(grid_fids)
        for feat in self.schematic.getFeatures(request):
            geom = feat.geometry()
            centroid = geom.centroid().asPoint()
            succes, value = self.tin.tin_at_xy(centroid.x(), centroid.y())
            if succes != 0:
                continue
            cur.execute(qry, (value, feat.id()))
        self.gutils.con.commit()


class LeveesElevation(ElevationCorrector):

    def __init__(self, gutils, lyrs):
        super(LeveesElevation, self).__init__(gutils, lyrs)

    def setup_layers(self):
        self.points = self.lyrs.data['user_elevation_points']['qlyr']
        self.lines = self.lyrs.data['user_levee_lines']['qlyr']
        self.polygons = self.lyrs.data['user_elevation_polygons']['qlyr']
        self.schematic = self.lyrs.data['levee_data']['qlyr']
        self.filter_expression = "SELECT * FROM {} WHERE membership = 'all' OR membership = 'levees';"

    def elevation_from_points(self, search_buffer):
        cur = self.gutils.con.cursor()
        for feat in self.lines.getFeatures():
            try:
                qry = 'UPDATE levee_data SET levcrest = ? WHERE fid = ?;'
                intervals = get_intervals(feat, self.points.getFeatures(), self.ELEVATION_FIELD, search_buffer)
            except TypeError:
                qry = 'UPDATE levee_data SET levcrest = levcrest + ? WHERE fid = ?;'
                intervals = get_intervals(feat, self.points.getFeatures(), self.CORRECTION_FIELD, search_buffer)
            interpolated = interpolate_along_line(feat, self.schematic.getFeatures(), intervals)
            try:
                for elev, fid in interpolated:
                    cur.execute(qry, (round(elev, 3), fid))
            except IndexError:
                continue
        self.gutils.con.commit()

    def elevation_from_lines(self):
        cur = self.gutils.con.cursor()
        for feat in self.lines.getFeatures():
            fid = feat['fid']
            elev = feat[self.ELEVATION_FIELD]
            cor = feat[self.CORRECTION_FIELD]
            qry = 'UPDATE levee_data SET levcrest = ? WHERE user_line_fid = ?;'
            if isinstance(elev, QPyNullVariant) and isinstance(cor, QPyNullVariant):
                continue
            elif not isinstance(elev, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
                val = elev + cor
            elif not isinstance(elev, QPyNullVariant) and isinstance(cor, QPyNullVariant):
                val = elev
            elif isinstance(elev, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
                qry = 'UPDATE levee_data SET levcrest = levcrest + ? WHERE user_line_fid = ?;'
                val = cor
            else:
                continue
            cur.execute(qry, (round(val, 3), fid))
        self.gutils.con.commit()

    def elevation_from_polygons(self):
        qry = 'UPDATE levee_data SET levcrest = ? WHERE fid = ?;'
        cur = self.gutils.con.cursor()
        for feat in self.lines.getFeatures():
            poly_values = polys2levees(feat, self.polygons, self.schematic, self.ELEVATION_FIELD, self.CORRECTION_FIELD)
            for elev, fid in poly_values:
                cur.execute(qry, (round(elev, 3), fid))
        self.gutils.con.commit()
