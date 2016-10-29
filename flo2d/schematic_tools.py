# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QgsSpatialIndex
from operator import itemgetter


def get_intervals(line_feature, point_layer, col_name, buffer_size):
    points = point_layer.getFeatures()
    lgeom = line_feature.geometry()
    tot_len = lgeom.length()
    buf = lgeom.buffer(buffer_size, 5)
    positions = {}
    for feat in points:
        pnt = feat.geometry()
        if buf.contains(pnt):
            pass
        else:
            continue
        pos = lgeom.lineLocatePoint(pnt) / tot_len
        val = feat[col_name]
        closest = lgeom.distance(pnt)
        if pos not in positions or closest < positions[pos][-1]:
            positions.values()
            positions[pos] = (pos, val, closest)
        else:
            pass
    snapped = (i[:-1] for i in sorted(positions.values(), key=itemgetter(0)))
    intervals = []
    try:
        start_distance, start_value = next(snapped)
        end_distance, end_value = next(snapped)
        while True:
            delta_distance = end_distance - start_distance
            delta_value = end_value - start_value
            interval = (start_distance, end_distance, delta_distance, start_value, end_value, delta_value)
            intervals.append(interval)
            start_distance, start_value = end_distance, end_value
            end_distance, end_value = next(snapped)
    except StopIteration:
        return intervals


def interpolate_along_line(line_feature, sampling_layer, intervals, id_col='fid', join_col='user_line_fid'):
    start, end = intervals[0], intervals[-1]
    lgeom = line_feature.geometry()
    lid = line_feature[id_col]
    tot_len = lgeom.length()
    fs = sampling_layer.getFeatures()
    sc = [(lgeom.lineLocatePoint(f.geometry().centroid()) / tot_len, f[id_col]) for f in fs if f[join_col] == lid]
    sc.sort()
    inter_iter = iter(intervals)
    snapped_iter = iter(sc)
    try:
        start_distance, end_distance, delta_distance, start_value, end_value, delta_value = next(inter_iter)
        position, fid = next(snapped_iter)
        while True:
            if start_distance < position < end_distance:
                segment_distance = position - start_distance
                coef = segment_distance / delta_distance
                value = start_value + delta_value * coef
                yield (value, fid)
            elif position == start_distance:
                yield (start_value, fid)
            elif position == end_value:
                yield (end_value, fid)
            elif position < start[0]:
                yield (start[3], fid)
            elif position > end[1]:
                yield (start[4], fid)
            else:
                start_distance, end_distance, delta_distance, start_value, end_value, delta_value = next(inter_iter)
                continue
            position, fid = next(snapped_iter)
    except StopIteration:
        return


def polys2levees(line_feature, poly_lyr, levees_lyr, value_col, id_col='fid', join_col='user_line_fid'):
    lgeom = line_feature.geometry()
    lid = line_feature[id_col]
    polys = poly_lyr.getFeatures()
    allfeatures = {feature.id(): feature for feature in polys}
    index = QgsSpatialIndex()
    map(index.insertFeature, allfeatures.itervalues())
    fids = index.intersects(lgeom.boundingBox())
    sel_polys = [allfeatures[fid] for fid in fids if allfeatures[fid].geometry().intersects(lgeom)]
    for feat in levees_lyr.getFeatures():
        if feat[join_col] == lid:
            pass
        else:
            continue
        center = feat.geometry().centroid()
        pos = lgeom.lineLocatePoint(center)
        pnt = lgeom.interpolate(pos)
        for poly in sel_polys:
            if poly.geometry().contains(pnt):
                yield (poly[value_col], feat[id_col])
                break
            else:
                pass


def bresenham_line(x1, y1, x2, y2):
    """Bresenham's Line Algorithm.
    Returns a list of [x,y] tuples. Works with integer coordinates.

    Based on impl from http://www.roguebasin.com/index.php?title=Bresenham%27s_Line_Algorithm
    """

    # Determine how steep the line is
    is_steep = abs(y2 - y1) > abs(x2 - x1)

    # Rotate line
    if is_steep:
        x1, y1 = y1, x1
        x2, y2 = y2, x2

    # Swap start and end points if necessary and store swap state
    swapped = False
    if x1 > x2:
        x1, x2 = x2, x1
        y1, y2 = y2, y1
        swapped = True

    # Calculate differentials
    dx = x2 - x1
    dy = y2 - y1

    # Calculate error
    error = int(dx / 2.0)
    ystep = 1 if y1 < y2 else -1

    # Iterate over bounding box generating points between start and end
    y = y1
    points = []
    for x in range(x1, x2 + 1):
        coord = (y, x) if is_steep else (x, y)
        points.append(coord)
        error -= abs(dy)
        if error < 0:
            y += ystep
            error += dx

    # Reverse the list if the coordinates were swapped
    if swapped:
        points.reverse()
    return points


def snap_line(x1, y1, x2, y2, cell_size, offset_x, offset_y):
    """
    Take line from (x1,y1) to (x2,y2) and generate list of cell coordinates
    covered by the line within the given grid.
    """

    def float_to_int_coords(x, y):
        xt = int(round(x / float(cell_size)))
        yt = int(round(y / float(cell_size)))
        return xt, yt

    def int_to_float_coords(xt, yt):
        x = xt * cell_size - offset_x
        y = yt * cell_size - offset_y
        return x, y

    xt1, yt1 = float_to_int_coords(x1, y1)
    xt2, yt2 = float_to_int_coords(x2, y2)

    points = bresenham_line(xt1, yt1, xt2, yt2)

    return [int_to_float_coords(x, y) for x, y in points]


def schematize_lines(line_layer, cell_size, offset_x, offset_y):
    lines = line_layer.getFeatures()
    for line in lines:
        segment = []
        try:
            vertices = line.geometry().asPolyline()
            iver = iter(vertices)
            x1, y1 = next(iver)
            x2, y2 = next(iver)
            while True:
                segment += snap_line(x1, y1, x2, y2, cell_size, offset_x, offset_y)
                x1, y1 = x2, y2
                x2, y2 = next(iver)
        except StopIteration:
            yield segment


def write_schematized(gutils, line_layer, cell_size):
    geom = gutils.single_centroid('1').strip('POINT()').split()
    x, y = float(geom[0]), float(geom[1])
    x_offset = round(x / cell_size) * cell_size - x
    y_offset = round(y / cell_size) * cell_size - y
    segments = schematize_lines(line_layer, cell_size, x_offset, y_offset)
    qry = '''INSERT INTO chan (geom) VALUES (AsGPB(ST_GeomFromText('LINESTRING({0})')))'''
    cursor = gutils.con.cursor()
    for line in segments:
        vertices = ','.join('{0} {1}'.format(x, y) for x, y in line)
        cursor.execute(qry.format(vertices))
    gutils.con.commit()
