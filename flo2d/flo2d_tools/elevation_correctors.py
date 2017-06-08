# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from PyQt4.QtCore import QPyNullVariant, QVariant
from qgis.core import QgsFeatureRequest, QgsField, QgsFeature, QgsGeometry, QgsVectorLayer, QgsMapLayerRegistry, QGis
from qgis.analysis import QgsZonalStatistics
from collections import defaultdict
from grid_tools import TINInterpolator, poly2grid, poly2poly, polygons_statistics
from schematic_tools import get_intervals, interpolate_along_line, polys2levees


class ElevationCorrector(object):

    ELEVATION_FIELD = 'elev'
    CORRECTION_FIELD = 'correction'
    VIRTUAL_SUM = 'elev_correction'

    def __init__(self, gutils, lyrs):
        self.gutils = gutils
        self.lyrs = lyrs

        self.user_points = None
        self.user_polygons = None

        self.filter_expression = ''
        self.field_expression = '''
        CASE 
        WHEN ("{0}" IS NOT NULL AND "{1}" IS NULL) THEN "{0}" 
        WHEN ("{0}" IS NULL AND "{1}" IS NOT NULL) THEN "{1}" 
        WHEN ("{0}" is NOT NULL AND "{1}" IS NOT NULL) THEN "{0}" + "{1}"
        END
        '''

    def setup_elevation_layers(self):
        self.user_points = self.lyrs.data['user_elevation_points']['qlyr']
        self.user_polygons = self.lyrs.data['user_elevation_polygons']['qlyr']

    def set_filter(self):
        self.user_points.setSubsetString(self.filter_expression.format('user_elevation_points'))
        self.user_polygons.setSubsetString(self.filter_expression.format('user_elevation_polygons'))

    def clear_filter(self):
        self.user_points.setSubsetString('')
        self.user_polygons.setSubsetString('')

    def add_virtual_sum(self, layer):
        expr = self.field_expression.format(self.ELEVATION_FIELD, self.CORRECTION_FIELD)
        field = QgsField(self.VIRTUAL_SUM, QVariant.Double)
        layer.addExpressionField(expr, field)

    def remove_virtual_sum(self, layer):
        index = layer.fieldNameIndex(self.VIRTUAL_SUM)
        layer.removeExpressionField(index)

    @staticmethod
    def duplicate_layer(vlayer, request=None):
        if request is None:
            feats = [feat for feat in vlayer.getFeatures()]
        else:
            feats = [feat for feat in vlayer.getFeatures(request)]
        vtype = vlayer.geometryType()
        if vtype == QGis.Point:
            uri_type = 'Point'
        elif vtype == QGis.Line:
            uri_type = 'LineString'
        elif vtype == QGis.Polygon:
            uri_type = 'Polygon'
        else:
            return
        epsg = vlayer.crs().authid()
        duplicate_name = '{}_duplicated'.format(vlayer.name())
        mem_layer = QgsVectorLayer('{}?crs={}'.format(uri_type, epsg), duplicate_name, 'memory')
        mem_layer_data = mem_layer.dataProvider()
        attr = vlayer.dataProvider().fields().toList()
        mem_layer_data.addAttributes(attr)
        mem_layer.updateFields()
        mem_layer_data.addFeatures(feats)
        return mem_layer


class LeveesElevation(ElevationCorrector):

    def __init__(self, gutils, lyrs):
        super(LeveesElevation, self).__init__(gutils, lyrs)
        self.schema_levees = None
        self.user_levees = None

    def setup_layers(self):
        self.setup_elevation_layers()
        self.user_levees = self.lyrs.data['user_levee_lines']['qlyr']
        self.schema_levees = self.lyrs.data['levee_data']['qlyr']
        self.filter_expression = "SELECT * FROM {} WHERE membership = 'all' OR membership = 'levees';"

    def elevation_from_points(self, search_buffer):
        cur = self.gutils.con.cursor()
        for feat in self.user_levees.getFeatures():
            try:
                qry = 'UPDATE levee_data SET levcrest = ? WHERE fid = ?;'
                intervals = get_intervals(feat, self.user_points.getFeatures(), self.ELEVATION_FIELD, search_buffer)
            except TypeError:
                qry = 'UPDATE levee_data SET levcrest = levcrest + ? WHERE fid = ?;'
                intervals = get_intervals(feat, self.user_points.getFeatures(), self.CORRECTION_FIELD, search_buffer)
            interpolated = interpolate_along_line(feat, self.schema_levees.getFeatures(), intervals)
            try:
                for elev, fid in interpolated:
                    cur.execute(qry, (round(elev, 3), fid))
            except IndexError:
                continue
        self.gutils.con.commit()

    def elevation_from_lines(self):
        cur = self.gutils.con.cursor()
        for feat in self.user_levees.getFeatures():
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
        for feat in self.user_levees.getFeatures():
            poly_values = polys2levees(feat, self.user_polygons, self.schema_levees, self.ELEVATION_FIELD, self.CORRECTION_FIELD)
            for elev, fid in poly_values:
                cur.execute(qry, (round(elev, 3), fid))
        self.gutils.con.commit()


class GridElevation(ElevationCorrector):

    def __init__(self, gutils, lyrs):
        super(GridElevation, self).__init__(gutils, lyrs)
        self.grid = None
        self.tin = None
        self.blocked_areas = None

    def setup_layers(self):
        self.setup_elevation_layers()
        self.grid = self.lyrs.data['grid']['qlyr']
        self.blocked_areas = self.lyrs.data['blocked_areas']['qlyr']
        self.filter_expression = "SELECT * FROM {} WHERE membership = 'all' OR membership = 'grid';"

    def elevation_from_polygons(self):
        set_qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
        add_qry = 'UPDATE grid SET elevation = elevation + ? WHERE fid = ?;'
        set_add_qry = 'UPDATE grid SET elevation = ? + ? WHERE fid = ?;'
        cur = self.gutils.con.cursor()
        for el, cor, fid in poly2grid(self.grid, self.user_polygons, None, True, False, self.ELEVATION_FIELD, self.CORRECTION_FIELD):

            el_null = isinstance(el, QPyNullVariant)
            cor_null = isinstance(cor, QPyNullVariant)
            if not el_null:
                el = round(el, 3)
            if not cor_null:
                cor = round(cor, 3)

            if not el_null and cor_null:
                cur.execute(set_qry, (el, fid))
            elif el_null and not cor_null:
                cur.execute(add_qry, (cor, fid))
            elif not el_null and not cor_null:
                cur.execute(set_add_qry, (el, cor, fid))

        self.gutils.con.commit()

    def elevation_from_tin(self):
        self.add_virtual_sum(self.user_points)
        self.tin = TINInterpolator(self.user_points, self.VIRTUAL_SUM)
        self.tin.setup_layer_data()
        grid_fids = [val[0] for val in poly2grid(self.grid, self.user_polygons, None, True, True)]
        cur = self.gutils.con.cursor()
        request = QgsFeatureRequest().setFilterFids(grid_fids)
        qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
        for feat in self.grid.getFeatures(request):
            geom = feat.geometry()
            centroid = geom.centroid().asPoint()
            succes, value = self.tin.tin_at_xy(centroid.x(), centroid.y())
            if succes != 0:
                continue
            cur.execute(qry, (round(value, 3), feat.id()))
        self.gutils.con.commit()
        self.remove_virtual_sum(self.user_points)

    def elevation_within_arf(self, calculation_type):
        if calculation_type == 'Mean':
            def calculation_method(vals): return sum(vals) / len(vals)
        elif calculation_type == 'Max':
            def calculation_method(vals): return max(vals)
        elif calculation_type == 'Min':
            def calculation_method(vals): return min(vals)
        else:
            raise ValueError
        cur = self.gutils.con.cursor()
        qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
        request = QgsFeatureRequest().setFilterExpression('"calc_arf" = 1')
        for fid, parts in poly2poly(self.blocked_areas, self.grid, request, 'fid', 'elevation'):
            gids, elevs, subareas = [], [], []
            for gid, elev, area in parts:
                gids.append(gid)
                elevs.append(elev)
            elevation = round(calculation_method(elevs), 3)
            for g in gids:
                cur.execute(qry, (elevation, g))
        self.gutils.con.commit()


class ExternalElevation(ElevationCorrector):

    def __init__(self, gutils, lyrs):
        super(ExternalElevation, self).__init__(gutils, lyrs)

        self.grid = None
        self.only_centroids = None

        self.polygons = None
        self.elevation_field = None
        self.correction_field = None

        self.statistics = None
        self.raster = None

        self.only_selected = None
        self.copy_features = None
        self.request = None

    def setup_internal(self):
        self.setup_elevation_layers()
        self.grid = self.lyrs.data['grid']['qlyr']

    def setup_external(self, polygon_lyr, predicate, only_selected=False, copy_features=False):
        self.polygons = polygon_lyr
        self.only_centroids = True if predicate == 'centroids within polygons' else False
        self.only_selected = only_selected
        if self.only_selected is True:
            self.request = QgsFeatureRequest().setFilterFids(self.polygons.selectedFeaturesIds())
        self.copy_features = copy_features

    def setup_attributes(self, elevation, correction):
        self.elevation_field = elevation
        self.correction_field = correction

    def setup_statistics(self, statistics, raster=None):
        self.statistics = statistics
        self.raster = raster

    def import_features(self, fids_values):
        copy_request = QgsFeatureRequest().setFilterFids(fids_values.keys())
        fields = self.user_polygons.fields()
        self.user_polygons.startEditing()
        for feat in self.polygons.getFeatures(copy_request):
            values = fids_values[feat.id()]
            new_feat = QgsFeature()
            new_feat.setFields(fields)
            poly_geom = feat.geometry().asPolygon()
            new_geom = QgsGeometry.fromPolygon(poly_geom)
            new_feat.setGeometry(new_geom)
            for key, val in values.items():
                new_feat.setAttribute(key, val)
            new_feat.setAttribute('membership', 'grid')
            self.user_polygons.addFeature(new_feat)
        self.user_polygons.commitChanges()
        self.user_polygons.updateExtents()
        self.user_polygons.triggerRepaint()
        self.user_polygons.removeSelection()

    def elevation_attributes(self):
        set_qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
        add_qry = 'UPDATE grid SET elevation = elevation + ? WHERE fid = ?;'
        set_add_qry = 'UPDATE grid SET elevation = ? + ? WHERE fid = ?;'
        poly_list = poly2grid(self.grid,
                              self.polygons,
                              self.request,
                              self.only_centroids,
                              True,
                              self.elevation_field,
                              self.correction_field)
        fids = {}
        qry_values = []
        for fid, el, cor, gid in poly_list:

            el_null = isinstance(el, QPyNullVariant)
            cor_null = isinstance(cor, QPyNullVariant)
            if not el_null:
                el = round(el, 3)
            if not cor_null:
                cor = round(cor, 3)

            if not el_null and cor_null:
                qry_values.append((set_qry, (el, gid)))
            elif el_null and not cor_null:
                qry_values.append((add_qry, (cor, gid)))
            elif not el_null and not cor_null:
                qry_values.append((set_add_qry, (el, cor, gid)))

            fids[fid] = {'elev': el, 'correction': cor}

        cur = self.gutils.con.cursor()
        for qry, vals in qry_values:
            cur.execute(qry, vals)
        self.gutils.con.commit()
        if self.copy_features is True:
            self.import_features(fids)

    def elevation_grid_statistics(self):
        if self.statistics == 'Mean':
            def calculation_method(vals): return sum(vals) / len(vals)
        elif self.statistics == 'Max':
            def calculation_method(vals): return max(vals)
        elif self.statistics == 'Min':
            def calculation_method(vals): return min(vals)
        else:
            raise ValueError
        cur = self.gutils.con.cursor()
        qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
        grid_gen = poly2grid(self.grid, self.polygons, self.request, self.only_centroids, True)
        fids_grids = defaultdict(list)
        fids_elevs = {}
        for fid, gid in grid_gen:
            fids_grids[fid].append(gid)
        for fid, grids_fids in fids_grids.items():
            grid_request = QgsFeatureRequest().setFilterFids(grids_fids)
            elevs = []
            for grid_feat in self.grid.getFeatures(grid_request):
                elevs.append(grid_feat['elevation'])
            elevation = round(calculation_method(elevs), 3)
            fids_elevs[fid] = {'elev': elevation}
            for g in grids_fids:
                cur.execute(qry, (elevation, g))
        self.gutils.con.commit()
        if self.copy_features is True:
            self.import_features(fids_elevs)

    def elevation_raster_statistics(self):
        if self.statistics == 'Mean':
            stats = QgsZonalStatistics.Mean
        elif self.statistics == 'Max':
            stats = QgsZonalStatistics.Max
        elif self.statistics == 'Min':
            stats = QgsZonalStatistics.Min
        else:
            raise ValueError

        self.polygons = self.duplicate_layer(self.polygons, self.request)
        QgsMapLayerRegistry.instance().addMapLayer(self.polygons)
        polygons_statistics(self.polygons, self.raster, stats)
        self.elevation_field = self.statistics.lower()
        self.correction_field = None
        self.request = None
        self.elevation_attributes()
        QgsMapLayerRegistry.instance().removeMapLayer(self.polygons)
