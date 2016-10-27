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
