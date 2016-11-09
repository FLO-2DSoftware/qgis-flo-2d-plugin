# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import math
from qgis.core import QgsGeometry, QgsPoint, QgsSpatialIndex, QgsRasterLayer, QgsRaster
from utils import is_number


def build_grid(boundary, cell_size):
    """
    Generator which creates grid with given cell size and inside given boundary layer.
    """
    half_size = cell_size * 0.5
    biter = boundary.getFeatures()
    feature = next(biter)
    fgeom = feature.geometry()
    bbox = fgeom.boundingBox()
    xmin = math.floor(bbox.xMinimum())
    xmax = math.ceil(bbox.xMaximum())
    ymax = math.ceil(bbox.yMaximum())
    ymin = math.floor(bbox.yMinimum())
    cols = int(math.ceil(abs(xmax - xmin) / cell_size))
    rows = int(math.ceil(abs(ymax - ymin) / cell_size))
    x = xmin + half_size
    y = ymax - half_size
    for col in xrange(cols):
        y_tmp = y
        for row in xrange(rows):
            if fgeom.contains(QgsPoint(x, y_tmp)):
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


def poly2grid(grid, polygons, value_column):
    """
    Generator for assigning values from any polygon layer to target grid layer.
    """
    polys = polygons.selectedFeatures() if polygons.selectedFeatureCount() > 0 else polygons.getFeatures()
    allfeatures = {feature.id(): feature for feature in polys}
    index = QgsSpatialIndex()
    map(index.insertFeature, allfeatures.itervalues())
    for feat in grid.getFeatures():
        geom = feat.geometry()
        centroid = geom.centroid()
        fids = index.intersects(centroid.boundingBox())
        for fid in fids:
            f = allfeatures[fid]
            isin = f.geometry().contains(centroid)
            if isin is True:
                yield (f[value_column], feat.id())
            else:
                pass


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
    area_polys = areas.selectedFeatures() if areas.selectedFeatureCount() > 0 else areas.getFeatures()
    allfeatures = {feature.id(): feature for feature in area_polys}
    index = QgsSpatialIndex()
    map(index.insertFeature, allfeatures.itervalues())
    features = grid.getFeatures()
    first = next(features)
    grid_area = first.geometry().area()
    grid_side = math.sqrt(grid_area)
    octagon_side = grid_side / 2.414
    half_square = grid_side * 0.5
    half_octagon = octagon_side * 0.5
    empty_wrf = (0,) * 8
    full_wrf = (1,) * 8
    for feat in grid.getFeatures():
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
                if arf > 0.95:
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


def square_grid(gutils, boundary):
    """
    Function for calculating and writing square grid into 'grid' table.
    """
    del_qry = 'DELETE FROM grid;'
    cellsize = gutils.execute('''SELECT value FROM cont WHERE name = "CELLSIZE";''').fetchone()[0]
    update_cellsize = 'UPDATE user_model_boundary SET cell_size = ?;'
    insert_qry = '''INSERT INTO grid (geom) VALUES (AsGPB(ST_GeomFromText('POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))')));'''
    gutils.execute(update_cellsize, (cellsize,))
    cellsize = float(cellsize)
    polygons = build_grid(boundary, cellsize)
    cur = gutils.con.cursor()
    cur.execute(del_qry)
    c = 0
    for poly in polygons:
        cur.execute(insert_qry.format(*poly))
        c += 1
    gutils.con.commit()
    return c


def update_roughness(gutils, grid, roughness, column_name, reset=False):
    """
    Updating roughness values inside 'grid' table
    """
    if reset is True:
        default = gutils.get_cont_par('MANNING')
        gutils.execute('UPDATE grid SET n_value=?;', (default,))
    else:
        pass
    qry = 'UPDATE grid SET n_value=? WHERE fid=?;'
    gutils.con.executemany(qry, poly2grid(grid, roughness, column_name))
    gutils.con.commit()


def update_elevation(gutils, grid, elev, column_name):
    """
    Updating elevation values inside 'grid' table
    """
    qry = 'UPDATE grid SET elevation=? WHERE fid=?;'
    gutils.con.executemany(qry, poly2grid(grid, elev, column_name))
    gutils.con.commit()


def evaluate_arfwrf(gutils, grid, areas):
    """
    Calculating and inserting ARF and WRF values into 'blocked_cells' table
    """
    del_cells = 'DELETE FROM blocked_cells;'
    qry_cells = '''INSERT INTO blocked_cells (geom, grid_fid, area_fid, arf, wrf1, wrf2, wrf3, wrf4, wrf5, wrf6, wrf7, wrf8) VALUES (AsGPB(ST_GeomFromText('{}')),?,?,?,?,?,?,?,?,?,?,?);'''
    gutils.execute(del_cells)
    cur = gutils.con.cursor()
    for row in calculate_arfwrf(grid, areas):
        point = row[0]
        gpb_qry = qry_cells.format(point)
        cur.execute(gpb_qry, row[1:])
    gutils.con.commit()


def raster2grid(grid, out_raster):
    """
    Generator for resampling and probing raster data within 'grid' features
    """
    probe_raster = QgsRasterLayer(out_raster)
    if not probe_raster.isValid():
        return

    for feat in grid.getFeatures():
        center = feat.geometry().centroid().asPoint()
        ident = probe_raster.dataProvider().identify(center, QgsRaster.IdentifyFormatValue)
        if ident.isValid():
            if is_number(ident.results()[1]):
                val = round(ident.results()[1], 3)
            else:
                val = None
            yield (val, feat.id())
    del probe_raster


def grid_has_empty_elev(gutils):
    """
    Return number of grid elements that have no elevation defined
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
