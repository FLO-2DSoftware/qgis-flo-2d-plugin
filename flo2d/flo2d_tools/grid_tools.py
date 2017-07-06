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
from collections import defaultdict
from subprocess import Popen, PIPE, STDOUT
from qgis.core import QgsFeature,  QgsGeometry, QgsPoint, QgsSpatialIndex, QgsRasterLayer, QgsRaster, QgsFeatureRequest
from qgis.analysis import QgsInterpolator, QgsTINInterpolator, QgsZonalStatistics
from PyQt4.QtCore import QPyNullVariant
from flo2d.utils import is_number


# GRID classes
class TINInterpolator(object):

    def __init__(self, point_lyr, field_name, memory=True):
        self.lyr = point_lyr
        self.field_name = field_name
        self.memory = memory
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

    def setup_probing(self):
        self.points_feats, self.points_index = spatial_index(self.points)
        if self.calculation_type == 'Mean':
            self.calculation_method = lambda vals: sum(vals) / len(vals)
        elif self.calculation_type == 'Max':
            self.calculation_method = lambda vals: max(vals)
        elif self.calculation_type == 'Min':
            self.calculation_method = lambda vals: min(vals)
        else:
            pass
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
    geos_geom = QgsGeometry.createGeometryEngine(geom.geometry())
    geos_geom.prepareGeometry()
    for col in xrange(cols):
        y_tmp = y
        for row in xrange(rows):
            pnt = QgsGeometry.fromPoint(QgsPoint(x, y_tmp))
            if geos_geom.intersects(pnt.geometry()):
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


def poly2grid(grid, polygons, request, use_centroids, get_fid, *columns):
    """
    Generator for assigning values from any polygon layer to target grid layer.
    """
    allfeatures, index = spatial_centroids_index(grid) if use_centroids is True else spatial_index(grid)

    polygon_features = polygons.getFeatures() if request is None else polygons.getFeatures(request)
    for feat in polygon_features:
        fid = feat.id()
        geom = feat.geometry()
        geos_geom = QgsGeometry.createGeometryEngine(geom.geometry())
        geos_geom.prepareGeometry()
        for gid in index.intersects(geom.boundingBox()):
            grid_feat = allfeatures[gid]
            other_geom = grid_feat.geometry()
            isin = geos_geom.contains(other_geom.geometry())
            if isin is not True:
                continue
            values = [fid] if get_fid is True else []
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
        if ident.isValid():
            if is_number(ident.results()[1]):
                val = round(ident.results()[1], 3)
            else:
                val = None
            yield (val, feat.id())


def rasters2centroids(vlayer, request, *raster_paths):
    """
    Generator for probing raster data by centroids.
    """
    features = vlayer.getFeatures() if request is None else vlayer.getFeatures(request)
    centroids = []
    for feat in features:
        fid = feat.id()
        center_point = feat.geometry().centroid().asPoint()
        centroids.append((fid, center_point))

    for pth in raster_paths:
        raster_values = []
        rlayer = QgsRasterLayer(pth)
        if not rlayer.isValid():
            continue
        raster_provider = rlayer.dataProvider()
        for fid, point in centroids:
            ident = raster_provider.identify(point, QgsRaster.IdentifyFormatValue)
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
    gutils.con.executemany(qry, poly2grid(grid, roughness, None, True, False, column_name))
    gutils.con.commit()


def modify_elevation(gutils, grid, elev):
    """
    Modifying elevation values inside 'grid' table.
    """
    set_qry = 'UPDATE grid SET elevation = ? WHERE fid = ?;'
    add_qry = 'UPDATE grid SET elevation = elevation + ? WHERE fid = ?;'
    set_add_qry = 'UPDATE grid SET elevation = ? + ? WHERE fid = ?;'
    for el, cor, fid in poly2grid(grid, elev, None, True, False, 'elev', 'correction'):
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
    """
    del_cells = 'DELETE FROM blocked_cells;'
    qry_cells = '''
    INSERT INTO blocked_cells
                (geom, grid_fid, area_fid, arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8) VALUES
                (AsGPB(ST_GeomFromText('{}')),?,?,?,?,?,?,?,?,?,?,?);'''
    gutils.execute(del_cells)
    cur = gutils.con.cursor()
    for row in calculate_arfwrf(grid, areas):
        point = row[0]
        gpb_qry = qry_cells.format(point)
        cur.execute(gpb_qry, row[1:])
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
