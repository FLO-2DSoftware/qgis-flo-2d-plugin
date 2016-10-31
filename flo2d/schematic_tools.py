# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

from qgis.core import QgsPoint, QgsSpatialIndex, QgsFeatureRequest, QgsVector
from operator import itemgetter
from grid_tools import get_intersecting_grid_elems
from math import pi

# octagon nodes to sides map
octagon_levee_dirs = {0:1, 1:5, 2:2, 3:6, 4:3, 5:7, 6:4, 7:8}

# octagon sides normal vectors
nvec = {0: QgsVector(0,1), 1: QgsVector(1,1), 2: QgsVector(1,0), 3: QgsVector(1,-1),
        4: QgsVector(0,-1), 5: QgsVector(-1,-1), 6: QgsVector(-1,0), 7: QgsVector(-1,1)}

levee_dir_pts = {
        1: (lambda x, y, square_half, octa_half: (x - octa_half, y + square_half, x + octa_half, y + square_half)),
        2: (lambda x, y, square_half, octa_half: (x + square_half, y + octa_half, x + square_half, y - octa_half)),
        3: (lambda x, y, square_half, octa_half: (x + octa_half, y - square_half, x - octa_half, y - square_half)),
        4: (lambda x, y, square_half, octa_half: (x - square_half, y - octa_half, x - square_half, y + octa_half)),
        5: (lambda x, y, square_half, octa_half: (x + octa_half, y + square_half, x + square_half, y + octa_half)),
        6: (lambda x, y, square_half, octa_half: (x + square_half, y - octa_half, x + octa_half, y - square_half)),
        7: (lambda x, y, square_half, octa_half: (x - octa_half, y - square_half, x - square_half, y - octa_half)),
        8: (lambda x, y, square_half, octa_half: (x - square_half, y + octa_half, x - octa_half, y + square_half))
}


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


def levee_grid_isect_pts(levee_fid, grid_fid, levee_lyr, grid_lyr, with_centroid=True):
    lfeat = levee_lyr.getFeatures(QgsFeatureRequest(levee_fid)).next()
    gfeat = grid_lyr.getFeatures(QgsFeatureRequest(grid_fid)).next()
    grid_centroid = gfeat.geometry().centroid().asPoint()
    lg_isect = gfeat.geometry().intersection(lfeat.geometry())
    pts = []
    if lg_isect.isMultipart():
        for part in lg_isect.asMultiPolyline():
            p1 = part[0]
            p2 = part[-1]
            pts.append((p1, p2))
    else:
        p1 = lg_isect.asPolyline()[0]
        p2 = lg_isect.asPolyline()[-1]
        pts.append((p1, p2))
    if with_centroid:
        return (pts, grid_centroid)
    else:
        return (pts)


def generate_schematic_levees(gutils, levee_lyr, grid_lyr):
    lg = get_intersecting_grid_elems(gutils, 'user_levee_lines')
    cell_size = float(gutils.get_cont_par('CELLSIZE'))
    schem_lines = {}
    gids = []
    nv = QgsVector(0, 1)
    scale = 0.9
    sh = cell_size * 0.5 * scale
    oh = sh / 2.414
    # for each line crossing a grid element
    for lid, gid in lg:
        pts, c = levee_grid_isect_pts(lid, gid, levee_lyr, grid_lyr)
        if not gid in gids:
            schem_lines[gid] = {}
            schem_lines[gid]['lines'] = {}
            schem_lines[gid]['centroid'] = c
            gids.append(gid)
        else:
            pass
        sides = []
        # for each entry and leaving point pair
        for pts_pair in pts:
            p1, p2 = pts_pair
            c_p1 = p1 - c
            c_p2 = p2 - c
            a = c_p1.angle(c_p2)
            a = 2 * pi + a if a < 0 else a
            # drawing direction (is it clockwise?)
            cw = a >= pi
            c_p1_a = c_p1.angle(nv)
            c_p1_a = 2 * pi + c_p1_a if c_p1_a < 0 else c_p1_a
            c_p2_a = c_p2.angle(nv)
            c_p2_a = 2 * pi + c_p2_a if c_p2_a < 0 else c_p2_a
            # nearest octagon nodes
            n1 = int(c_p1_a / (pi / 4)) % 8
            n2 = int(c_p2_a / (pi / 4)) % 8
            # if entry and leaving octagon node are identical, skip the pair (no levee seg)
            if n1 == n2:
                # print '{}: ({:.2f}, {:.2f}), n1 = n2 = {}, skipping'.format(gid, c_p1.angle(nv)*180/pi, c_p2.angle(nv)*180/pi, n1)
                continue
            else:
                # print "{}: {:.2f}->{}, {:.2f}->{}".format( gid, c_p1.angle(nv)*180/pi, n1, c_p2.angle(nv)*180/pi, n2)
                pass
            # starting and ending octagon side for current pts pair
            s1 = (n1 + 1 if cw else n1) % 8
            s2 = (n2 if cw else n2 + 1) % 8
            # add sides from s1 to s2 for creating the segments
            sides.append(s2)
            while s1 != s2:
                sides.insert(0, s1)
                s1 = (s1 + 1 if cw else s1 - 1) % 8
        sides = set(sides)
        schem_lines[gid]['lines'][lid] = sides

    del_sql = '''DELETE FROM levee_data WHERE user_line_fid IS NOT NULL;'''
    ins_sql = '''INSERT INTO levee_data (grid_fid, ldir, user_line_fid, geom) VALUES (?,?,?, AsGPB(ST_GeomFromText(?)));'''

    # create levee segments for distinct levee directions in each grid element
    grid_levee_seg = {}
    data = []
    for gid, gdata in schem_lines.iteritems():
        grid_levee_seg[gid] = {}
        grid_levee_seg[gid]['sides'] = {}
        grid_levee_seg[gid]['centroid'] = gdata['centroid']
        for lid, sides in gdata['lines'].iteritems():
            for side in sides:
                if not side in grid_levee_seg[gid]['sides'].keys():
                    grid_levee_seg[gid]['sides'][side] = lid
                    ldir = octagon_levee_dirs[side]
                    c = gdata['centroid']
                    data.append((
                        gid,
                        ldir,
                        lid,
                        'LINESTRING({0} {1}, {2} {3})'.format(*levee_dir_pts[ldir](c.x(), c.y(), sh, oh))
                    ))
    gutils.con.execute(del_sql)
    gutils.con.executemany(ins_sql, data)
    gutils.con.commit()


def perp2side(vec, side, tol):
    '''Check, with the given tol [deg], if the vector is perpendicular to the given octagon side'''
    tol = tol * pi / 180
    if abs(nvec[side].angle(vec)) <= tol or abs(nvec[side].rotateBy(pi).angle(vec)) <= tol:
        return True
    else:
        return False
