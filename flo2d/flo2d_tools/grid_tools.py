# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import math
import uuid

from PyQt4.QtGui import QMessageBox, QProgressBar
from flo2d.user_communication import UserCommunication
from collections import defaultdict
from subprocess import Popen, PIPE, STDOUT
from qgis.core import QgsFeature, QgsGeometry, QgsPoint, QgsSpatialIndex, QgsRasterLayer, QgsRaster, QgsFeatureRequest
from qgis.analysis import QgsInterpolator, QgsTINInterpolator, QgsZonalStatistics
from PyQt4.QtCore import QPyNullVariant
from flo2d.utils import is_number

# GRID classes
class TINInterpolator(object):

    def __init__(self, point_lyr, field_name):
        self.lyr = point_lyr
        self.field_name = field_name
        self.lyr_data = None
        self.interpolator = None

    def setup_layer_data(self):
        index = self.lyr.fieldNameIndex(self.field_name)
        self.lyr_data = QgsInterpolator.LayerData()
        self.lyr_data.interpolationAttribute = index
        self.lyr_data.vectorLayer = self.lyr
        self.lyr_data.mInputType = 0
        self.lyr_data.zCoordInterpolation = False
        self.interpolator = QgsTINInterpolator([self.lyr_data])

    def tin_at_xy(self, x, y):
        success, value = self.interpolator.interpolatePoint(x, y)
        return success, value


class ZonalStatistics(object):

    def __init__(self, gutils, grid_lyr, point_lyr, field_name, calculation_type, search_distance=0):
        self.gutils = gutils
        self.grid = grid_lyr
        self.points = point_lyr
        self.field = field_name
        self.calculation_type = calculation_type
        self.search_distance = search_distance
        self.uid = uuid.uuid4()
        self.points_feats = None
        self.points_index = None
        self.calculation_method = None
        self.gap_raster = None
        self.filled_raster = None
        self.tmp = os.environ['TMP']
        self.setup_probing()

    @staticmethod
    def calculate_mean(vals):
        result = sum(vals) / len(vals)
        return result

    @staticmethod
    def calculate_max(vals):
        result = max(vals)
        return result

    @staticmethod
    def calculate_min(vals):
        result = min(vals)
        return result

    def setup_probing(self):
        self.points_feats, self.points_index = spatial_index(self.points)
        if self.calculation_type == 'Mean':
            self.calculation_method = self.calculate_mean
        elif self.calculation_type == 'Max':
            self.calculation_method = self.calculate_max
        elif self.calculation_type == 'Min':
            self.calculation_method = self.calculate_min
        self.gap_raster = os.path.join(self.tmp, 'gap_raster_{0}.tif'.format(self.uid))
        self.filled_raster = os.path.join(self.tmp, 'filled_raster_{0}.tif'.format(self.uid))
        self.gutils.execute('UPDATE grid SET elevation = NULL;')

    def remove_rasters(self):
        try:
            os.remove(self.gap_raster)
            os.remove(self.filled_raster)
        except OSError as e:
            pass

    def points_elevation(self):
        """
        Method for calculating grid cell values from point layer.
        """
        for feat in self.grid.getFeatures():
            geom = feat.geometry()
            geos_geom = QgsGeometry.createGeometryEngine(geom.geometry())
            geos_geom.prepareGeometry()
            fids = self.points_index.intersects(geom.boundingBox())
            points = []
            for fid in fids:
                point_feat = self.points_feats[fid]
                other_geom = point_feat.geometry()
                isin = geos_geom.intersects(other_geom.geometry())
                if isin is True:
                    points.append(point_feat[self.field])
                else:
                    pass
            try:
                yield round(self.calculation_method(points), 3), feat['fid']
            except (ValueError, ZeroDivisionError) as e:
                pass

    def rasterize_grid(self):
        grid_extent = self.grid.extent()
        corners = (grid_extent.xMinimum(), grid_extent.yMinimum(), grid_extent.xMaximum(), grid_extent.yMaximum())

        command = 'gdal_rasterize'
        field = '-a elevation'
        rtype = '-ot Float64'
        rformat = '-of GTiff'
        extent = '-te {0} {1} {2} {3}'.format(*corners)
        res = '-tr {0} {0}'.format(self.gutils.get_cont_par('CELLSIZE'))
        nodata = '-a_nodata NULL'
        compress = '-co COMPRESS=LZW'
        predictor = '-co PREDICTOR=1'
        vlayer = '-l grid'
        gpkg = '"{0}"'.format(self.grid.source().split('|')[0])
        raster = '"{0}"'.format(self.gap_raster)

        parameters = (command, field, rtype, rformat, extent, res, nodata, compress, predictor, vlayer, gpkg, raster)
        cmd = ' '.join(parameters)
        success = False
        loop = 0
        out = None
        while success is False:
            proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
            out = proc.communicate()
            if os.path.exists(self.gap_raster):
                success = True
            else:
                loop += 1
            if loop > 3:
                raise Exception
        return cmd, out

    def fill_nodata(self):
        search = '-md {0}'.format(self.search_distance) if self.search_distance > 0 else ''
        cmd = 'gdal_fillnodata {0} "{1}" "{2}"'.format(search, self.gap_raster, self.filled_raster)
        proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        out = proc.communicate()
        return cmd, out

    def null_elevation(self):
        req = QgsFeatureRequest().setFilterExpression('"elevation" IS NULL')
        elev_fid = raster2grid(self.grid, self.filled_raster, request=req)
        return elev_fid

    def set_elevation(self, elev_fid):
        """
        Setting elevation values inside 'grid' table.
        """
        set_qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
        cur = self.gutils.con.cursor()
        for el, fid in elev_fid:
            cur.execute(set_qry, (el, fid))
        self.gutils.con.commit()


class ZonalStatisticsOther(object):

    def __init__(self, gutils, grid_lyr, grid_field, point_lyr, field_name, calculation_type, search_distance=0):
        self.gutils = gutils
        self.grid = grid_lyr
        self.points = point_lyr
        self.grid_field = grid_field
        self.field = field_name
        self.calculation_type = calculation_type
        self.search_distance = search_distance
        self.uid = uuid.uuid4()
        self.points_feats = None
        self.points_index = None
        self.calculation_method = None
        self.gap_raster = None
        self.filled_raster = None
        self.tmp = os.environ['TMP']
        self.setup_probing()

    @staticmethod
    def calculate_mean(vals):
        result = sum(vals) / len(vals)
        return result

    @staticmethod
    def calculate_max(vals):
        result = max(vals)
        return result

    @staticmethod
    def calculate_min(vals):
        result = min(vals)
        return result

    def setup_probing(self):
        self.points_feats, self.points_index = spatial_index(self.points)
        if self.calculation_type == 'Mean':
            self.calculation_method = self.calculate_mean
        elif self.calculation_type == 'Max':
            self.calculation_method = self.calculate_max
        elif self.calculation_type == 'Min':
            self.calculation_method = self.calculate_min
        self.gap_raster = os.path.join(self.tmp, 'gap_raster_{0}.tif'.format(self.uid))
        self.filled_raster = os.path.join(self.tmp, 'filled_raster_{0}.tif'.format(self.uid))

        if self.grid_field == 'water_elevation':
            self.gutils.execute('UPDATE grid SET water_elevation = NULL;')
        elif self.grid_field == 'flow_depth':
            self.gutils.execute('UPDATE grid SET flow_depth = NULL;')


    def remove_rasters(self):
        try:
            os.remove(self.gap_raster)
            os.remove(self.filled_raster)
        except OSError as e:
            pass

    def points_elevation(self):
        """
        Method for calculating grid cell values from point layer.
        """
        for feat in self.grid.getFeatures():
            geom = feat.geometry()
            geos_geom = QgsGeometry.createGeometryEngine(geom.geometry())
            geos_geom.prepareGeometry()
            fids = self.points_index.intersects(geom.boundingBox())
            points = []
            for fid in fids:
                point_feat = self.points_feats[fid]
                other_geom = point_feat.geometry()
                isin = geos_geom.intersects(other_geom.geometry())
                if isin is True:
                    points.append(point_feat[self.field])
                else:
                    pass
            try:
                yield round(self.calculation_method(points), 3), feat['fid']
            except (ValueError, ZeroDivisionError) as e:
                pass

    def rasterize_grid(self):
        grid_extent = self.grid.extent()
        corners = (grid_extent.xMinimum(), grid_extent.yMinimum(), grid_extent.xMaximum(), grid_extent.yMaximum())

        command = 'gdal_rasterize'
        field = '-a elevation'
        rtype = '-ot Float64'
        rformat = '-of GTiff'
        extent = '-te {0} {1} {2} {3}'.format(*corners)
        res = '-tr {0} {0}'.format(self.gutils.get_cont_par('CELLSIZE'))
        nodata = '-a_nodata NULL'
        compress = '-co COMPRESS=LZW'
        predictor = '-co PREDICTOR=1'
        vlayer = '-l grid'
        gpkg = '"{0}"'.format(self.grid.source().split('|')[0])
        raster = '"{0}"'.format(self.gap_raster)

        parameters = (command, field, rtype, rformat, extent, res, nodata, compress, predictor, vlayer, gpkg, raster)
        cmd = ' '.join(parameters)
        success = False
        loop = 0
        out = None
        while success is False:
            proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
            out = proc.communicate()
            if os.path.exists(self.gap_raster):
                success = True
            else:
                loop += 1
            if loop > 3:
                raise Exception
        return cmd, out

    def fill_nodata(self):
        search = '-md {0}'.format(self.search_distance) if self.search_distance > 0 else ''
        cmd = 'gdal_fillnodata {0} "{1}" "{2}"'.format(search, self.gap_raster, self.filled_raster)
        proc = Popen(cmd, shell=True, stdin=open(os.devnull), stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        out = proc.communicate()
        return cmd, out

    def null_elevation(self):
        req = QgsFeatureRequest().setFilterExpression('"water_elevation" IS NULL')
        elev_fid = raster2grid(self.grid, self.filled_raster, request=req)
        return elev_fid


    def set_other(self, elev_fid):
        """
        Setting values inside 'grid' table.
        """
        if self.grid_field == 'water_elevation':
            set_qry = 'UPDATE grid SET water_elevation = ? WHERE fid = ?;'
        elif self.grid_field == 'flow_depth':
            set_qry = 'UPDATE grid SET flow_depth = ? WHERE fid = ?;'

        cur = self.gutils.con.cursor()
        for el, fid in elev_fid:
            cur.execute(set_qry, (el, fid))
        self.gutils.con.commit()



def debugMsg(msg_string):
    msgBox = QMessageBox()
    msgBox.setText(msg_string)
    msgBox.exec_()


def polygons_statistics(vlayer, rlayer, statistics):
    rlayer_src = rlayer.source()
    zonalstats = QgsZonalStatistics(vlayer, rlayer_src, '', 1, statistics)
    res = zonalstats.calculateStatistics(None)
    return res


# GRID functions
def spatial_index(vlayer):
    """
    Creating spatial index over collection of features.
    """
    allfeatures = {}
    index = QgsSpatialIndex()
    for feat in vlayer.getFeatures():
        feat_copy = QgsFeature(feat)
        allfeatures[feat.id()] = feat_copy
        index.insertFeature(feat_copy)
    return allfeatures, index


def spatial_centroids_index(vlayer):
    """
    Creating spatial index over collection of features centroids.
    """
    allfeatures = {}
    index = QgsSpatialIndex()
    for feat in vlayer.getFeatures():
        feat_copy = QgsFeature(feat)
        feat_copy.setGeometry(feat_copy.geometry().centroid())
        allfeatures[feat.id()] = feat_copy
        index.insertFeature(feat_copy)
    return allfeatures, index


def intersection_spatial_index(vlayer):
    """
    Creating optimized for intersections spatial index over collection of features.
    """
    allfeatures = {}
    index = QgsSpatialIndex()
    max_fid = max(vlayer.allFeatureIds()) + 1
    for feat in vlayer.getFeatures():
        geom = feat.geometry()
        new_geoms = divide_geom(geom)
        new_fid = True if len(new_geoms) > 1 else False
        for g in new_geoms:
            engine = QgsGeometry.createGeometryEngine(g.geometry())
            engine.prepareGeometry()
            feat_copy = QgsFeature(feat)
            feat_copy.setGeometry(g)
            if new_fid is True:
                fid = max_fid
                feat_copy.setFeatureId(fid)
                max_fid += 1
            else:
                fid = feat.id()
            allfeatures[fid] = (feat_copy, engine)
            index.insertFeature(feat_copy)

    return allfeatures, index


def count_polygon_vertices(geom):
    """
    Function for counting polygon vertices.
    """
    c = 0
    for part in geom.asPolygon():
        c += len(part)
    return c


def divide_geom(geom, threshold=1000):
    """
    Recursive function for dividing complex polygons into smaller chunks using geometry bounding box.
    """
    if count_polygon_vertices(geom) <= threshold:
        return [geom]
    bbox = geom.boundingBox()
    center_x, center_y = bbox.center()
    xmin, ymin = bbox.xMinimum(), bbox.yMinimum()
    xmax, ymax = bbox.xMaximum(), bbox.yMaximum()
    center_point = QgsPoint(center_x, center_y)
    s1 = QgsGeometry.fromPolygon(
        [[center_point, QgsPoint(center_x, ymin), QgsPoint(xmin, ymin), QgsPoint(xmin, center_y), center_point]])
    s2 = QgsGeometry.fromPolygon(
        [[center_point, QgsPoint(xmin, center_y), QgsPoint(xmin, ymax), QgsPoint(center_x, ymax), center_point]])
    s3 = QgsGeometry.fromPolygon(
        [[center_point, QgsPoint(center_x, ymax), QgsPoint(xmax, ymax), QgsPoint(xmax, center_y), center_point]])
    s4 = QgsGeometry.fromPolygon(
        [[center_point, QgsPoint(xmax, center_y), QgsPoint(xmax, ymin), QgsPoint(center_x, ymin), center_point]])

    new_geoms = []
    for s in [s1, s2, s3, s4]:
        part = geom.intersection(s)
        if part.isEmpty():
            continue
        if part.isMultipart():
            single_geoms = [QgsGeometry.fromPolygon(g) for g in part.asMultiPolygon()]
            for sg in single_geoms:
                new_geoms += divide_geom(sg, threshold)
            continue
        count = count_polygon_vertices(part)
        if count <= threshold:
            new_geoms.append(part)
        else:
            new_geoms += divide_geom(part, threshold)
    return new_geoms


def build_grid(boundary, cell_size):
    """
    Generator which creates grid with given cell size and inside given boundary layer.
    """
    half_size = cell_size * 0.5
    biter = boundary.getFeatures()
    feature = next(biter)
    geom = feature.geometry()
    bbox = geom.boundingBox()
    xmin = math.floor(bbox.xMinimum())
    xmax = math.ceil(bbox.xMaximum())
    ymax = math.ceil(bbox.yMaximum())
    ymin = math.floor(bbox.yMinimum())
    cols = int(math.ceil(abs(xmax - xmin) / cell_size))
    rows = int(math.ceil(abs(ymax - ymin) / cell_size))
    x = xmin + half_size
    y = ymax - half_size
    geos_geom_engine = QgsGeometry.createGeometryEngine(geom.geometry())
    geos_geom_engine.prepareGeometry()
    for col in xrange(cols):
        y_tmp = y
        for row in xrange(rows):
            pnt = QgsGeometry.fromPoint(QgsPoint(x, y_tmp))
            if geos_geom_engine.intersects(pnt.geometry()):
                poly = (
                    x - half_size, y_tmp - half_size,
                    x + half_size, y_tmp - half_size,
                    x + half_size, y_tmp + half_size,
                    x - half_size, y_tmp + half_size,
                    x - half_size, y_tmp - half_size
                )
                yield poly
            else:
                pass
            y_tmp -= cell_size
        x += cell_size


def poly2grid(grid, polygons, request, use_centroids, get_fid, threshold, *columns):
    """
    Generator for assigning values from any polygon layer to target grid layer.
    """
    try:
        grid_feats = grid.getFeatures()
        first = next(grid_feats)
        grid_area = first.geometry().area()
    except StopIteration:
        return

    if use_centroids is True:
        def geos_compare(geos1, geos2):
            return True
    else:
        def geos_compare(geos1, geos2):
            inter_area = geos1.intersection(geos2).area()
            if inter_area / grid_area < threshold:
                return False
            else:
                return True

    if get_fid is True:
        def default_value(feat_id):
            return [feat_id]
    else:
        def default_value(feat_id):
            return []

    allfeatures, index = spatial_centroids_index(grid) if use_centroids is True else spatial_index(grid)
    polygon_features = polygons.getFeatures() if request is None else polygons.getFeatures(request)

    for feat in polygon_features:
        fid = feat.id()
        geom = feat.geometry()
        geos_geom_engine = QgsGeometry.createGeometryEngine(geom.geometry())
        geos_geom_engine.prepareGeometry()
        for gid in index.intersects(geom.boundingBox()):
            grid_feat = allfeatures[gid]
            other_geom = grid_feat.geometry()
            other_geom_geos = other_geom.geometry()
            isin = geos_geom_engine.intersects(other_geom_geos)
            if isin is not True or geos_compare(geos_geom_engine, other_geom_geos) is False:
                continue
            values = default_value(fid)
            for col in columns:
                try:
                    val = feat[col]
                except KeyError:
                    val = QPyNullVariant(float)
                values.append(val)
            values.append(gid)
            values = tuple(values)
            yield values


def poly2poly(base_polygons, polygons, request, area_percent, *columns):
    """
    Generator which calculates base polygons intersections with another polygon layer.
    """
    allfeatures, index = spatial_index(polygons)

    base_features = base_polygons.getFeatures() if request is None else base_polygons.getFeatures(request)
    for feat in base_features:
        base_geom = feat.geometry()
        base_area = base_geom.area()
        fids = index.intersects(base_geom.boundingBox())
        if not fids:
            continue
        base_fid = feat.id()
        base_parts = []
        for fid in fids:
            f = allfeatures[fid]
            fgeom = f.geometry()
            inter = fgeom.intersects(base_geom)
            if inter is False:
                continue
            intersection_geom = fgeom.intersection(base_geom)
            subarea = intersection_geom.area() if area_percent is False else intersection_geom.area() / base_area
            values = tuple(f[col] for col in columns) + (subarea,)
            base_parts.append(values)
        yield base_fid, base_parts


def poly2poly_geos(base_polygons, polygons, request, *columns):
    """
    Generator which calculates base polygons intersections with another polygon layer.
    """
    allfeatures, index = intersection_spatial_index(polygons)

    base_features = base_polygons.getFeatures() if request is None else base_polygons.getFeatures(request)
    for feat in base_features:
        base_geom = feat.geometry()
        fids = index.intersects(base_geom.boundingBox())
        if not fids:
            continue
        base_fid = feat.id()
        base_area = base_geom.area()
        base_geom_geos = base_geom.geometry()
        base_geom_engine = QgsGeometry.createGeometryEngine(base_geom_geos)
        base_geom_engine.prepareGeometry()
        base_parts = []
        for fid in fids:
            f, other_geom_engine = allfeatures[fid]
            inter = other_geom_engine.intersects(base_geom_geos)
            if inter is False:
                continue
            if other_geom_engine.contains(base_geom_geos):
                subarea = 1
            elif base_geom_engine.contains(f.geometry().geometry()):
                subarea = other_geom_engine.area() / base_area
            else:
                intersection_geom = other_geom_engine.intersection(base_geom_geos)
                subarea = intersection_geom.area() / base_area
            values = tuple(f[col] for col in columns) + (subarea,)
            base_parts.append(values)
        yield base_fid, base_parts


def grid_sections(grid, polygons, request, *columns):
    """
    Function for finding intersections of polygon layer within grid layer.
    """
    try:
        grid_feats = grid.getFeatures()
        first = next(grid_feats)
        grid_area = first.geometry().area()
    except StopIteration:
        return

    allfeatures, index = intersection_spatial_index(grid)
    polygon_features = polygons.getFeatures() if request is None else polygons.getFeatures(request)

    grid_parts = defaultdict(list)
    for feat in polygon_features:
        geom = feat.geometry()
        ids = index.intersects(geom.boundingBox())
        if not ids:
            continue
        geos_geom = geom.geometry()
        geom_engine = QgsGeometry.createGeometryEngine(geos_geom)
        geom_engine.prepareGeometry()
        attributes = tuple(feat[col] for col in columns)

        for gid in ids:
            grid_feat, other_geom_engine = allfeatures[gid]
            other_geom = grid_feat.geometry()
            other_geom_geos = other_geom.geometry()
            if geom_engine.contains(other_geom_geos):
                subarea = 1
            elif other_geom_engine.contains(geos_geom):
                subarea = other_geom_geos.area() / grid_area
            elif geom_engine.intersects(other_geom_geos):
                subarea = geom_engine.intersection(other_geom_geos).area() / grid_area
            else:
                continue
            values = attributes + (subarea,)
            grid_parts[gid].append(values)

    return grid_parts


def cluster_polygons(polygons, *columns):
    """
    Functions for clustering polygons by common attributes.
    """
    clusters = defaultdict(list)
    for feat in polygons.getFeatures():
        geom_poly = feat.geometry().asPolygon()
        attrs = tuple(feat[col] for col in columns)
        clusters[attrs].append(QgsGeometry.fromPolygon(geom_poly))
    return clusters


def clustered_features(polygons, fields, *columns, **columns_map):
    """
    Generator which returns features with clustered geometries.
    """
    clusters = cluster_polygons(polygons, *columns)
    target_columns = [columns_map[c] if c in columns_map else c for c in columns]
    for attrs, geom_list in clusters.items():

        if len(geom_list) > 1:
            geom = QgsGeometry.unaryUnion(geom_list)
            if geom.isMultipart():
                poly_geoms = [QgsGeometry.fromPolygon(g) for g in geom.asMultiPolygon()]
            else:
                poly_geoms = [geom]
        else:
            poly_geoms = geom_list
        for new_geom in poly_geoms:
            new_feat = QgsFeature()
            new_feat.setGeometry(new_geom)
            new_feat.setFields(fields)
            for col, val in zip(target_columns, attrs):
                new_feat.setAttribute(col, val)
            yield new_feat


def calculate_arfwrf(grid, areas):
    """
    Generator which calculates ARF and WRF values based on polygons representing blocked areas.
    """
    sides = (
        (lambda x, y, square_half, octa_half: (x - octa_half, y + square_half, x + octa_half, y + square_half)),
        (lambda x, y, square_half, octa_half: (x + square_half, y + octa_half, x + square_half, y - octa_half)),
        (lambda x, y, square_half, octa_half: (x + octa_half, y - square_half, x - octa_half, y - square_half)),
        (lambda x, y, square_half, octa_half: (x - square_half, y - octa_half, x - square_half, y + octa_half)),
        (lambda x, y, square_half, octa_half: (x + octa_half, y + square_half, x + square_half, y + octa_half)),
        (lambda x, y, square_half, octa_half: (x + square_half, y - octa_half, x + octa_half, y - square_half)),
        (lambda x, y, square_half, octa_half: (x - octa_half, y - square_half, x - square_half, y - octa_half)),
        (lambda x, y, square_half, octa_half: (x - square_half, y + octa_half, x - octa_half, y + square_half))
    )
    allfeatures, index = spatial_index(areas)
    features = grid.getFeatures()
    first = next(features)
    grid_area = first.geometry().area()
    grid_side = math.sqrt(grid_area)
    octagon_side = grid_side / 2.414
    half_square = grid_side * 0.5
    half_octagon = octagon_side * 0.5
    empty_wrf = (0,) * 8
    full_wrf = (1,) * 8
    features.rewind()
    for feat in features:
        geom = feat.geometry()
        fids = index.intersects(geom.boundingBox())
        for fid in fids:
            f = allfeatures[fid]
            fgeom = f.geometry()
            farf = int(f['calc_arf'])
            fwrf = int(f['calc_wrf'])
            inter = fgeom.intersects(geom)
            if inter is True:
                areas_intersection = fgeom.intersection(geom)
                arf = round(areas_intersection.area() / grid_area, 2) if farf == 1 else 0
                centroid = geom.centroid()
                centroid_wkt = centroid.exportToWkt()
                if arf >= 0.9:
                    yield (centroid_wkt, feat.id(), f.id(), 1) + (full_wrf if fwrf == 1 else empty_wrf)
                    continue
                else:
                    pass
                grid_center = centroid.asPoint()
                wrf_s = (f(grid_center.x(), grid_center.y(), half_square, half_octagon) for f in sides)
                wrf_geoms = (QgsGeometry.fromPolyline([QgsPoint(x1, y1), QgsPoint(x2, y2)]) for x1, y1, x2, y2 in wrf_s)
                if fwrf == 1:
                    wrf = (round(line.intersection(fgeom).length() / octagon_side, 2) for line in wrf_geoms)
                else:
                    wrf = empty_wrf
                yield (centroid_wkt, feat.id(), f.id(), arf) + tuple(wrf)
            else:
                pass

def calculate_spatial_variable(grid, areas):
    """
    Generator which calculates values based on polygons representing values.
    """
#     debugMsg("Inside calculate_spatial_variable 1")

    allfeatures, index = spatial_index(areas)
    features = grid.getFeatures()
    for feat in features:  #for each grid feature
        geom = feat.geometry() #cell square (a polygon)
        fids = index.intersects(geom.boundingBox()) #c
        for fid in fids:
            f = allfeatures[fid]
            fgeom = f.geometry()
            inter = fgeom.intersects(geom)
            if inter is True:
#                 areas_intersection = fgeom.intersection(geom)
#                 arf = round(areas_intersection.area() / grid_area, 2) if farf == 1 else 0
                centroid = geom.centroid()
                centroid_wkt = centroid.exportToWkt()
                yield (f.id(), feat.id())
            else:
                pass

def raster2grid(grid, out_raster, request=None):
    """
    Generator for probing raster data within 'grid' features.
    """
    probe_raster = QgsRasterLayer(out_raster)
    if not probe_raster.isValid():
        return

    features = grid.getFeatures() if request is None else grid.getFeatures(request)
    for feat in features:
        center = feat.geometry().centroid().asPoint()
        ident = probe_raster.dataProvider().identify(center, QgsRaster.IdentifyFormatValue)
        # ident is the value of the query provided by the identify method of the dataProvider.
        if ident.isValid():
            if is_number(ident.results()[1]):
                val = round(ident.results()[1], 3)
            else:
                val = None
            yield (val, feat.id())


def rasters2centroids(vlayer, request, *raster_paths):
    """
    Generator for probing raster data by centroids.

    Parameters:
    -----------
        vlayer: usually the grid layer.
        request:
        *raster_pathts: list of ASCII files (with path).

    """
    features = vlayer.getFeatures() if request is None else vlayer.getFeatures(request)
    centroids = []
    for feat in features:
        fid = feat.id()
        center_point = feat.geometry().centroid().asPoint()
        centroids.append((fid, center_point))

    # 'centroids' has the coordinates (x,y) of the centroids of all features of vlayer (ususlly the grid layer)
    for pth in raster_paths:
        raster_values = []
        rlayer = QgsRasterLayer(pth) # rlayer is an instance of the layer constructed from file pth (from list raster_paths).
                                     # Loads (or assigns a raster style), populates its bands, calculates its extend,
                                     # determines if the layers is gray, paletted, or multiband, assign sensible
                                     # defaults for the red, green, blue and gray bands.
        if not rlayer.isValid():
            continue
        raster_provider = rlayer.dataProvider()
        for fid, point in centroids:
            ident = raster_provider.identify(point, QgsRaster.IdentifyFormatValue)
            # ident is the value of the query provided by the identify method of the dataProvider.
            if ident.isValid():
                if is_number(ident.results()[1]):
                    val = round(ident.results()[1], 3)
                else:
                    val = None
                raster_values.append((val, fid))
        yield raster_values


# Tools which use GeoPackageUtils instance
def square_grid(gutils, boundary):
    """
    Function for calculating and writing square grid into 'grid' table.
    """
    del_qry = 'DELETE FROM grid;'
    cellsize = gutils.execute('''SELECT value FROM cont WHERE name = "CELLSIZE";''').fetchone()[0]
    update_cellsize = 'UPDATE user_model_boundary SET cell_size = ?;'
    insert_qry = '''INSERT INTO grid (geom) VALUES {};'''
    gpb = '''(AsGPB(ST_GeomFromText('POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))')))'''
    gutils.execute(update_cellsize, (cellsize,))
    cellsize = float(cellsize)
    polygons = (gpb.format(*poly) for poly in build_grid(boundary, cellsize))
    gutils.execute(del_qry)
    gutils.execute(insert_qry.format(','.join(polygons)))


def update_roughness(gutils, grid, roughness, column_name, reset=False):
    """
    Updating roughness values inside 'grid' table.
    """
    if reset is True:
        default = gutils.get_cont_par('MANNING')
        gutils.execute('UPDATE grid SET n_value=?;', (default,))
    else:
        pass
    qry = 'UPDATE grid SET n_value=? WHERE fid=?;'
    gutils.con.executemany(qry, poly2grid(grid, roughness, None, True, False, 1, column_name))
    gutils.con.commit()


def modify_elevation(gutils, grid, elev):
    """
    Modifying elevation values inside 'grid' table.
    """
    set_qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
    add_qry = 'UPDATE grid SET elevation = elevation + ? WHERE fid = ?;'
    set_add_qry = 'UPDATE grid SET elevation = ? + ? WHERE fid = ?;'
    for el, cor, fid in poly2grid(grid, elev, None, True, False, 1, 'elev', 'correction'):
        if not isinstance(el, QPyNullVariant) and isinstance(cor, QPyNullVariant):
            gutils.con.execute(set_qry, (el, fid))
        elif isinstance(el, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
            gutils.con.execute(add_qry, (cor, fid))
        elif not isinstance(el, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
            gutils.con.execute(set_add_qry, (el, cor, fid))
        else:
            pass
    gutils.con.commit()

def evaluate_arfwrf(gutils, grid, areas):
    """
    Calculating and inserting ARF and WRF values into 'blocked_cells' table.

    Parameters
    ----------

    gutils:
        the GeoPackageUtils class for the database handling:
        creation on cursor objects, their execution, commits to the tables, etc.

    grid:
        the grid layer.

    areas:
        the user blocked areas.

    """
    del_cells = 'DELETE FROM blocked_cells;'
    qry_cells = '''
    INSERT INTO blocked_cells
                (geom, grid_fid, area_fid, arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8) VALUES
                (AsGPB(ST_GeomFromText('{}')),?,?,?,?,?,?,?,?,?,?,?);'''
    gutils.execute(del_cells)
    cur = gutils.con.cursor()
    for row in calculate_arfwrf(grid, areas):
        # "row" is a tuple like  (u'Point (368257 1185586)', 1075L, 1L, 0.06, 0.0, 1.0, 0.0, 0.0, 0.14, 0.32, 0.0, 0.0)
        # with a POINT and the values of arf and wrfs for a single cell

        point = row[0]   # Fist element of tuple "row" is a POINT (centroid of cell?)

        gpb_qry = qry_cells.format(point)   # This new database command (operation not query) includes the actual point:
                                            #     INSERT INTO blocked_cells
                                            #     (geom, grid_fid, area_fid, arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8) VALUES
                                            #     (AsGPB(ST_GeomFromText('Point (368257 1185486)')),?,?,?,?,?,?,?,?,?,?,?);

        cur.execute(gpb_qry, row[1:])       # Applies the INSERT command with the data from the "row[1:]" tuple.

        gutils.con.commit()                 # Commits operation performed to the table "blocked_cells" using cursor "cur",
                                            # which means creating (INSERT) a row to the table with the values calculated in "calculate_arfwrf".

def evaluate_spatial_tolerance(gutils, grid, areas):
    """
    Calculating and inserting tolerance values into 'tolspatial_cells' table.
    """
    del_cells = 'DELETE FROM tolspatial_cells;'
    qry_cells = '''
    INSERT INTO tolspatial_cells (area_fid, grid_fid)  VALUES (?,?);'''

    gutils.execute(del_cells)
    cur = gutils.con.cursor()
    for row in calculate_spatial_variable(grid, areas):
        point = row[0]
        gpb_qry = qry_cells.format(point)
        cur.execute(qry_cells, row)
    gutils.con.commit()

def evaluate_spatial_buildings_adjustment_factor(gutils, grid, areas):
    self.uc.show_warn('Assignment of building areas to building polygons. Not implemented yet!')

def evaluate_spatial_froude(gutils, grid, areas):
    """
    Calculating and inserting fraude values into 'fpfroude_cells' table.
    """
    del_cells = 'DELETE FROM fpfroude_cells;'
    qry_cells = '''
    INSERT INTO fpfroude_cells (area_fid, grid_fid) VALUES (?,?);'''

    gutils.execute(del_cells)
    cur = gutils.con.cursor()
    for row in calculate_spatial_variable(grid, areas):
        point = row[0]
        gpb_qry = qry_cells.format(point)
        cur.execute(qry_cells, row)
    gutils.con.commit()


def evaluate_spatial_shallow(gutils, grid, areas):
    """
    Calculating and inserting shallow-n values into 'spatialshallow_cells' table.
    """
    del_cells = 'DELETE FROM spatialshallow_cells;'
    qry_cells = '''
    INSERT INTO spatialshallow_cells (area_fid, grid_fid) VALUES (?,?);'''

    gutils.execute(del_cells)
    cur = gutils.con.cursor()
    for row in calculate_spatial_variable(grid, areas):
        point = row[0]
        gpb_qry = qry_cells.format(point)
        cur.execute(qry_cells, row)
    gutils.con.commit()


def evaluate_spatial_gutter(gutils, grid, areas):
    """
    Calculating and inserting gutter values into 'gutter_cells' table.
    """
    del_cells = 'DELETE FROM gutter_cells;'
    qry_cells = '''
    INSERT INTO gutter_cells (area_fid, grid_fid)  VALUES (?,?);'''

    gutils.execute(del_cells)
    cur = gutils.con.cursor()
    for row in calculate_spatial_variable(grid, areas):
        point = row[0]
        gpb_qry = qry_cells.format(point)
        cur.execute(qry_cells, row)
    gutils.con.commit()

def evaluate_spatial_noexchange(gutils, grid, areas):
    """
    Calculating and inserting noexchange values into 'noexchange_chan_cells' table.
    """
    del_cells = 'DELETE FROM noexchange_chan_cells;'
    qry_cells = '''
    INSERT INTO noexchange_chan_cells (area_fid, grid_fid)  VALUES (?,?);'''

    gutils.execute(del_cells)
    cur = gutils.con.cursor()
    for row in calculate_spatial_variable(grid, areas):
        point = row[0]
        gpb_qry = qry_cells.format(point)
        cur.execute(qry_cells, row)
    gutils.con.commit()

def grid_has_empty_elev(gutils):
    """
    Return number of grid elements that have no elevation defined.
    """
    qry = '''SELECT count(*) FROM grid WHERE elevation IS NULL;'''
    res = gutils.execute(qry)
    try:
        n = res.next()
        return n[0]
    except StopIteration:
        return None


def fid_from_grid(gutils, table_name, table_fids=None, grid_center=False, switch=False, *extra_fields):
    """
    Get a list of grid elements fids that intersect the given tables features.
    Optionally, users can specify a list of table_fids to be checked.
    """
    grid_geom = 'ST_Centroid(GeomFromGPB(g1.geom))' if grid_center is True else 'GeomFromGPB(g1.geom)'
    grid_data = 'g1.fid, ' + ', '.join(('g1.{}'.format(fld) for fld in extra_fields)) if extra_fields else 'g1.fid'
    qry = '''
    SELECT
        g2.fid, {0}
    FROM
        grid AS g1, {1} AS g2
    WHERE g1.ROWID IN (
            SELECT id FROM rtree_grid_geom
            WHERE
                ST_MinX(GeomFromGPB(g2.geom)) <= maxx AND
                ST_MaxX(GeomFromGPB(g2.geom)) >= minx AND
                ST_MinY(GeomFromGPB(g2.geom)) <= maxy AND
                ST_MaxY(GeomFromGPB(g2.geom)) >= miny)
    AND
        ST_Intersects({2}, GeomFromGPB(g2.geom))
    '''
    qry = qry.format(grid_data, table_name, grid_geom)
    if table_fids:
        qry += 'AND g2.fid IN ({}) '.format(', '.join(f for f in table_fids))
    else:
        pass
    first, second = (1, 0) if switch is True else (0, 1)
    qry += '''ORDER BY g2.fid, g1.fid;'''
    grid_elems = ((row[first], row[second]) + tuple(row[2:]) for row in gutils.execute(qry))
    return grid_elems



def highlight_selected_segment(layer, id):
    feat_selection=[]
    for feature in layer.getFeatures():
        if feature.id() == id:
            feat_selection.append(feature.id())
            break
    layer.setSelectedFeatures(feat_selection)

def highlight_selected_xsection_a(gutils, layer, xs_id):
    qry = '''SELECT id FROM chan_elems WHERE fid = ?;'''
    xs = gutils.execute(qry, (xs_id,)).fetchone()
    feat_selection=[]
    for feature in layer.getFeatures():
        if feature.id() == xs[0]:
            feat_selection.append(feature.id())
            break
    layer.setSelectedFeatures(feat_selection)


def highlight_selected_xsection_b(layer, xs_id):
    feat_selection=[]
    for feature in layer.getFeatures():
        if feature.id() == xs_id:
            feat_selection.append(feature.id())
            break
    layer.setSelectedFeatures(feat_selection)


# def highlight_selected_xsection(layer, xs_id):
#     self.chan_elems = self.lyrs.data['chan_elems']['qlyr']
#     qry = '''SELECT id FROM chan_elems WHERE fid = ?;'''
#     xs = self.gutils.execute(qry, (xs_id,)).fetchone()
#     self.feat_selection=[]
#     for feature in self.chan_elems.getFeatures():
#         if feature.id() == xs[0]:
#             self.feat_selection.append(feature.id())
#             break
#     self.chan_elems.setSelectedFeatures(self.feat_selection)







