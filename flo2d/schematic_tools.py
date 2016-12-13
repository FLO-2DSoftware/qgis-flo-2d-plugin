# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2016 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import traceback
from operator import itemgetter
from collections import defaultdict, OrderedDict
from math import pi
from PyQt4.QtCore import QPyNullVariant
from qgis.core import QGis, QgsSpatialIndex, QgsFeature, QgsFeatureRequest, QgsVector, QgsGeometry, QgsPoint
from grid_tools import spatial_index, fid_from_grid


# Levees tools
def get_intervals(line_feature, point_layer, col_value, buffer_size):
    """
    Function which calculates intervals and assigning values based on intersection between line and snapped points.
    Points are selected by line buffer and filtered by the distance from the line feature.
    """
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
        val = feat[col_value]
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
    """
    Generator for interpolating values of sampling features centroids snapped to interpolation line.
    Line intervals list needs to be calculated first and derived as a generator parameter.
    """
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
            elif position == end_distance:
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


def polys2levees(line_feature, poly_lyr, levees_lyr, value_col, correct_val, id_col='fid', join_col='user_line_fid'):
    """
    Generator for assigning elevation values from polygons to levees.
    Levee sides centroids are snapped to the user levee line feature and next tested for intersecting with polygons.
    """
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
        levcrest = feat['levcrest']
        center = feat.geometry().centroid()
        pos = lgeom.lineLocatePoint(center)
        pnt = lgeom.interpolate(pos)
        for poly in sel_polys:
            if poly.geometry().contains(pnt):
                abs_val, cor = poly[value_col], poly[correct_val]
                if not isinstance(abs_val, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
                    poly_val = abs_val + cor
                elif not isinstance(abs_val, QPyNullVariant) and isinstance(cor, QPyNullVariant):
                    poly_val = abs_val
                elif isinstance(abs_val, QPyNullVariant) and not isinstance(cor, QPyNullVariant):
                    poly_val = cor + levcrest
                else:
                    continue
                yield (poly_val, feat[id_col])
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
        return pts, grid_centroid
    else:
        return pts, None


def levee_schematic(lid_gid_elev, levee_lyr, grid_lyr):
    schem_lines = {}
    gids = []
    nv = QgsVector(0, 1)
    # for each line crossing a grid element
    for lid, gid, elev in lid_gid_elev:
        pts, c = levee_grid_isect_pts(lid, gid, levee_lyr, grid_lyr)
        if gid not in gids:
            schem_lines[gid] = {}
            schem_lines[gid]['lines'] = {}
            schem_lines[gid]['centroid'] = c
            schem_lines[gid]['elev'] = elev
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
                continue
            else:
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
    return schem_lines


def generate_schematic_levees(gutils, levee_lyr, grid_lyr):
    # octagon nodes to sides map
    octagon_levee_dirs = {0: 1, 1: 5, 2: 2, 3: 6, 4: 3, 5: 7, 6: 4, 7: 8}
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
    lid_gid_elev = fid_from_grid(gutils, 'user_levee_lines', None, False, False, 'elevation')
    cell_size = float(gutils.get_cont_par('CELLSIZE'))
    scale = 0.9
    # square half
    sh = cell_size * 0.5 * scale
    # octagon half
    oh = sh / 2.414
    schem_lines = levee_schematic(lid_gid_elev, levee_lyr, grid_lyr)

    del_sql = '''DELETE FROM levee_data WHERE user_line_fid IS NOT NULL;'''
    ins_sql = '''INSERT INTO levee_data (grid_fid, ldir, levcrest, user_line_fid, geom)
                 VALUES (?,?,?,?, AsGPB(ST_GeomFromText(?)));'''

    # create levee segments for distinct levee directions in each grid element
    grid_levee_seg = {}
    data = []
    for gid, gdata in schem_lines.iteritems():
        elev = gdata['elev']
        grid_levee_seg[gid] = {}
        grid_levee_seg[gid]['sides'] = {}
        grid_levee_seg[gid]['centroid'] = gdata['centroid']
        for lid, sides in gdata['lines'].iteritems():
            for side in sides:
                if side not in grid_levee_seg[gid]['sides'].keys():
                    grid_levee_seg[gid]['sides'][side] = lid
                    ldir = octagon_levee_dirs[side]
                    c = gdata['centroid']
                    data.append((
                        gid,
                        ldir,
                        elev,
                        lid,
                        'LINESTRING({0} {1}, {2} {3})'.format(*levee_dir_pts[ldir](c.x(), c.y(), sh, oh))
                    ))
    gutils.con.execute(del_sql)
    gutils.con.executemany(ins_sql, data)
    gutils.con.commit()


# Line schematizing tools
def bresenham_line(x1, y1, x2, y2):
    """
    Bresenham's Line Algorithm.
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
        xt = int(round((x + offset_x) / float(cell_size)))
        yt = int(round((y + offset_y) / float(cell_size)))
        return xt, yt

    def int_to_float_coords(xt, yt):
        x = xt * cell_size - offset_x
        y = yt * cell_size - offset_y
        return x, y

    xt1, yt1 = float_to_int_coords(x1, y1)
    xt2, yt2 = float_to_int_coords(x2, y2)

    points = bresenham_line(xt1, yt1, xt2, yt2)

    return [int_to_float_coords(x, y) for x, y in points]


def schematize_lines(lines, cell_size, offset_x, offset_y, feats_only=False, get_id=False):
    """
    Generator for finding grid centroids coordinates for each schematized line segment.
    Calculations are done using Bresenham's Line Algorithm.
    """
    line_features = lines.getFeatures() if feats_only is False else lines
    for line in line_features:
        segment = []
        try:
            vertices = line.geometry().asPolyline()
            iver = iter(vertices)
            x1, y1 = next(iver)
            x2, y2 = next(iver)
            vals = [x for x in snap_line(x1, y1, x2, y2, cell_size, offset_x, offset_y)]
            segment += vals
            while True:
                x1, y1 = x2, y2
                x2, y2 = next(iver)
                vals = [x for x in snap_line(x1, y1, x2, y2, cell_size, offset_x, offset_y)][1:]
                segment += vals
        except StopIteration:
            if get_id is True:
                yield line.id(), segment
            else:
                yield segment


def calculate_offset(gutils, cell_size):
    """
    Finding offset of grid squares centers which is formed after switching from float to integers.
    Rounding to integers is needed for Bresenham's Line Algorithm.
    """
    geom = gutils.single_centroid('1').strip('POINT()').split()
    x, y = float(geom[0]), float(geom[1])
    x_offset = round(x / cell_size) * cell_size - x
    y_offset = round(y / cell_size) * cell_size - y
    return x_offset, y_offset


def inject_points(line_geom, points):
    """
    Function for inserting points located on line geometry as line vertexes.
    """
    new_line = line_geom.asPolyline()
    iline = iter(line_geom.asPolyline())
    ipoints = iter(points)
    pnt = next(ipoints)
    xy = next(iline)
    distance = line_geom.lineLocatePoint(QgsGeometry.fromPoint(pnt))
    vdistance = line_geom.lineLocatePoint(QgsGeometry.fromPoint(xy))
    shift = 0
    index = 0
    try:
        while True:
            if vdistance == distance:
                pnt = next(ipoints)
                xy = next(iline)
                distance = line_geom.lineLocatePoint(QgsGeometry.fromPoint(pnt))
                vdistance = line_geom.lineLocatePoint(QgsGeometry.fromPoint(xy))
                index += 1
            elif vdistance < distance:
                xy = next(iline)
                vdistance = line_geom.lineLocatePoint(QgsGeometry.fromPoint(xy))
                index += 1
            elif vdistance > distance:
                new_line.insert(index + shift, pnt)
                pnt = next(ipoints)
                distance = line_geom.lineLocatePoint(QgsGeometry.fromPoint(pnt))
                shift += 1
    except StopIteration:
        return new_line


def schematize_channels(gutils, line_layer, cell_size):
    """
    Calculating and writing schematized channels into the 'chan' table.
    """
    x_offset, y_offset = calculate_offset(gutils, cell_size)
    segments = schematize_lines(line_layer, cell_size, x_offset, y_offset)
    del_sql = '''DELETE FROM chan WHERE user_line_fid IS NOT NULL;'''
    insert_sql = '''INSERT INTO chan (geom, user_line_fid) VALUES (AsGPB(ST_GeomFromText('LINESTRING({0})')), ?)'''
    gutils.execute(del_sql)
    cursor = gutils.con.cursor()
    seen = set()
    for i, line in enumerate(segments, 1):
        vertices = ','.join(('{0} {1}'.format(*xy) for xy in line if xy not in seen and not seen.add(xy)))
        cursor.execute(insert_sql.format(vertices), (i,))
    gutils.con.commit()


# Streets schematizing tools
def populate_directions(coords, grids):
    """
    Function for populating streets directions inside each grid cell.
    """
    try:
        start, end = (0, 0)
        igrids = iter(grids)
        x1, y1 = next(igrids)
        x2, y2 = next(igrids)
        while True:
            if x1 == x2 and y1 < y2:
                start = 1
                end = 3
            elif x1 < x2 and y1 == y2:
                start = 2
                end = 4
            elif x1 == x2 and y1 > y2:
                start = 3
                end = 1
            elif x1 > x2 and y1 == y2:
                start = 4
                end = 2
            elif x1 < x2 and y1 < y2:
                start = 5
                end = 7
            elif x1 < x2 and y1 > y2:
                start = 6
                end = 8
            elif x1 > x2 and y1 > y2:
                start = 7
                end = 5
            elif x1 > x2 and y1 < y2:
                start = 8
                end = 6
            else:
                pass
            coords[(x1, y1)].add(start)
            coords[(x2, y2)].add(end)
            x1, y1 = x2, y2
            x2, y2 = next(igrids)
    except StopIteration:
        return


def schematize_streets(gutils, line_layer, cell_size):
    """
    Calculating and writing schematized streets into the 'street_seg' table.
    """
    streets_sql = '''INSERT INTO streets (fid) VALUES (?);'''
    seg_sql = '''INSERT INTO street_seg (geom, str_fid) VALUES (AsGPB(ST_GeomFromText('MULTILINESTRING({0})')), ?)'''
    elems_sql = '''INSERT INTO street_elems (seg_fid, istdir) VALUES (?,?)'''
    gpb_part = '''({0} {1}, {2} {3})'''
    half_cell = cell_size * 0.5
    gutils.clear_tables('streets', 'street_seg', 'street_elems')
    functions = {
        1: (lambda x, y, shift: (x, y + shift)),
        2: (lambda x, y, shift: (x + shift, y)),
        3: (lambda x, y, shift: (x, y - shift)),
        4: (lambda x, y, shift: (x - shift, y)),
        5: (lambda x, y, shift: (x + shift, y + shift)),
        6: (lambda x, y, shift: (x + shift, y - shift)),
        7: (lambda x, y, shift: (x - shift, y - shift)),
        8: (lambda x, y, shift: (x - shift, y + shift))
    }
    x_offset, y_offset = calculate_offset(gutils, cell_size)
    fid_segments = schematize_lines(line_layer, cell_size, x_offset, y_offset, get_id=True)
    cursor = gutils.con.cursor()
    fid_coords = {}
    coords = defaultdict(set)
    # Populating directions within each grid cell
    for fid, grids in fid_segments:
        populate_directions(coords, grids)
        # Assigning user line fid for each grid centroid coordinates
        for xy in coords.iterkeys():
            if xy not in fid_coords:
                fid_coords[xy] = fid
            else:
                continue
        cursor.execute(streets_sql, (fid,))
    for i, (xy, directions) in enumerate(coords.iteritems(), 1):
        x1, y1 = xy
        xy_dir = []
        for d in directions:
            cursor.execute(elems_sql, (i, d))
            xy_dir.append(functions[d](x1, y1, half_cell))
        multiline = ','.join((gpb_part.format(x1, y1, x2, y2) for x2, y2 in xy_dir))
        gpb_insert = seg_sql.format(multiline)
        cursor.execute(gpb_insert, (fid_coords[xy],))
    gutils.con.commit()
    fid_grid = fid_from_grid(gutils, 'street_seg', grid_center=True, switch=True)
    grid_sql = '''UPDATE street_seg SET igridn = ? WHERE fid = ?;'''
    gutils.execute_many(grid_sql, fid_grid)
    update_streets = '''
    UPDATE streets SET
        stname = (SELECT name FROM user_streets WHERE fid = streets.fid),
        notes = (SELECT notes FROM user_streets WHERE fid = streets.fid);'''
    update_street_seg = '''
    UPDATE street_seg SET
        depex = (SELECT curb_height FROM user_streets WHERE fid = street_seg.str_fid),
        stman = (SELECT n_value FROM user_streets WHERE fid = street_seg.str_fid),
        elstr = (SELECT elevation FROM user_streets WHERE fid = street_seg.str_fid);'''
    update_street_elems = '''
        UPDATE street_elems SET
            widr = (
                    SELECT us.street_width
                    FROM user_streets AS us, street_seg AS seg
                    WHERE us.fid = seg.str_fid AND street_elems.seg_fid = seg.fid);
                    '''
    crop_seg_sql = '''DELETE FROM street_seg WHERE igridn IS NULL;'''
    crop_elem_sql = '''DELETE FROM street_elems WHERE seg_fid NOT IN (SELECT fid FROM street_seg);'''
    gutils.execute(update_streets)
    gutils.execute(update_street_seg)
    gutils.execute(update_street_elems)
    gutils.execute(crop_seg_sql)
    gutils.execute(crop_elem_sql)


# Left bank and cross sections schematizing tools
def bank_lines(centerline_feature, domain_feature, xs_features):
    """
    Calculating left and right bank lines from intersection of river center line, 1D Domain and cross sections.
    Trimming and sorting cross sections.
    """
    allfeatures = {feature.id(): feature for feature in xs_features}
    index = QgsSpatialIndex()
    map(index.insertFeature, allfeatures.itervalues())
    domain = domain_feature.geometry()
    centerline = centerline_feature.geometry()
    geom1 = QgsGeometry.fromPolygon(domain.asPolygon())
    fids = index.intersects(geom1.boundingBox())
    cross_sections = [allfeatures[fid] for fid in fids if allfeatures[fid].geometry().intersects(geom1)]
    cross_sections.sort(key=lambda cs: centerline.lineLocatePoint(cs.geometry().intersection(centerline)))
    # Reshaping domain polygon
    start_xs = cross_sections[0]
    end_xs = cross_sections[-1]
    geom1.reshapeGeometry(start_xs.geometry().asPolyline())
    geom1.reshapeGeometry(end_xs.geometry().asPolyline())
    # Trimming center line and cross sections to reshaped domain
    trimmed_centerline = geom1.intersection(centerline)
    trim_xs(cross_sections, domain)
    # Splitting domain on left and right side using center line
    geom2 = geom1.splitGeometry(centerline.asPolyline(), 0)[1][0]
    if geom1.intersects(QgsGeometry.fromPoint(start_xs.geometry().vertexAt(0))):
        left_part = geom1
        right_part = geom2
    else:
        left_part = geom2
        right_part = geom1
    # Converting sides to lines
    left = left_part.convertToType(QGis.Line)
    right = right_part.convertToType(QGis.Line)
    # Erasing center line part from sides
    left_line = left.symDifference(trimmed_centerline)
    right_line = right.symDifference(trimmed_centerline)
    # Removing first and last vertex from sides
    llen = len(left_line.asPolyline()) - 1
    rlen = len(right_line.asPolyline()) - 1
    left_line.deleteVertex(llen)
    right_line.deleteVertex(rlen)
    left_line.deleteVertex(0)
    right_line.deleteVertex(0)
    # Flip bank lines if direction is inverted
    end_xs_geom = end_xs.geometry()
    if left_line.vertexAt(0) == end_xs_geom.vertexAt(0):
        nodes = left_line.asPolyline()
        nodes.reverse()
        left_line = QgsGeometry.fromPolyline(nodes)
    if right_line.vertexAt(0) == end_xs_geom.vertexAt(1):
        nodes = right_line.asPolyline()
        nodes.reverse()
        right_line = QgsGeometry.fromPolyline(nodes)
    return left_line, right_line, cross_sections


def trim_xs(xs_features, poly_geom):
    """
    Trimming xs features list to poly_geom boundaries.
    """
    for xs in xs_features:
        xs_geom = xs.geometry()
        trimmed = xs_geom.intersection(poly_geom)
        xs.setGeometry(trimmed)


def bank_stations(sorted_xs, left_line, right_line):
    """
    Finding crossing points between bank lines and cross sections.
    """
    fids = []
    left_points = []
    right_points = []
    for xs in sorted_xs:
        xs_geom = xs.geometry()
        xs_line = xs_geom.asPolyline()
        start = QgsGeometry.fromPoint(xs_line[0])
        end = QgsGeometry.fromPoint(xs_line[-1])
        left_cross = left_line.nearestPoint(start)
        right_cross = right_line.nearestPoint(end)
        left_points.append(left_cross.asPoint())
        right_points.append(right_cross.asPoint())
        fids.append(xs['fid'])
    return fids, left_points, right_points


def schematize_points(points, cell_size, x_offset, y_offset):
    """
    Using Bresenham's Line Algorithm on list of points.
    """
    feat = QgsFeature()
    geom = QgsGeometry.fromPolyline(points)
    feat.setGeometry(geom)
    # One line only
    lines = (feat,)
    segments = tuple(schematize_lines(lines, cell_size, x_offset, y_offset, feats_only=True))
    segment = segments[0]
    return segment


def closest_nodes(segment_points, bank_points):
    """
    Getting closest vertexes (with its indexes) to the bank points.
    """
    segment_geom = QgsGeometry.fromPolyline(segment_points)
    nodes = [segment_geom.closestVertex(pnt)[:2] for pnt in bank_points]
    return nodes


def interpolate_xs(left_segment, left_nodes, right_points, fids):
    """
    Interpolating cross sections using left segment points, left closest nodes and cross sections right points.
    """
    isegment = iter(left_segment)
    ileft_nodes = iter(left_nodes)
    iright_points = iter(right_points)
    ifid = iter(fids)

    vertex = next(isegment)
    first_left_node, first_idx = next(ileft_nodes)
    second_left_node, second_idx = next(ileft_nodes)
    first_right_point = next(iright_points)
    second_right_point = next(iright_points)

    start_point = None
    end_point = None
    xs_fid = next(ifid)
    interpolated = 0
    i = 0
    try:
        while True:
            if i == first_idx:
                start_point = first_left_node
                azimuth = first_left_node.azimuth(first_right_point)
                if azimuth < 0:
                    azimuth += 360
                closest_angle = round(azimuth / 45) * 45
                rotation = closest_angle - azimuth
                end_geom = QgsGeometry.fromPoint(first_right_point)
                end_geom.rotate(rotation, start_point)
                end_point = end_geom.asPoint()
            elif i < second_idx:
                delta = vertex - start_point
                start_point = vertex
                end_point += delta
                interpolated = 1
            elif i == second_idx:
                first_left_node, first_idx = second_left_node, second_idx
                first_right_point = second_right_point
                xs_fid = next(ifid)
                interpolated = 0
                try:
                    second_left_node, second_idx = next(ileft_nodes)
                    second_right_point = next(iright_points)
                except StopIteration:
                    i = first_idx
                continue
            yield [start_point, end_point, xs_fid, interpolated]
            i += 1
            vertex = next(isegment)
    except StopIteration:
        return


def schematize_xs(inter_xs, cell_size, x_offset, y_offset):
    """
    Schematizing interpolated cross sections using Bresenham's Line Algorithm.
    """
    try:
        while True:
            xs = next(inter_xs)
            points = xs[:2]
            attrs = xs[2:]
            org_fid, interpolated = attrs
            xs_segments = schematize_points(points, cell_size, x_offset, y_offset)
            x1, y1 = xs_segments[0]
            x2, y2 = xs_segments[-1]
            yield x1, y1, x2, y2, org_fid, interpolated
    except StopIteration:
        return


def clip_schema_xs(schema_xs):
    """
    Clipping schematized cross sections between each other.
    """
    # Clipping between original cross sections and creating spatial index on them.
    allfeatures = {}
    index = QgsSpatialIndex()
    previous = OrderedDict()
    first_clip_xs = []
    for xs in schema_xs:
        x1, y1, x2, y2, org_fid, interpolated = xs
        if interpolated == 1:
            first_clip_xs.append(xs)
            continue
        geom = QgsGeometry.fromPolyline([QgsPoint(x1, y1), QgsPoint(x2, y2)])
        for key, prev_geom in previous.items():
            cross = geom.intersects(prev_geom)
            if cross is False:
                previous.popitem(last=False)
            else:
                geom.splitGeometry(prev_geom.asPolyline(), 0)
        end = geom.asPolyline()[-1]
        x2, y2 = end.x(), end.y()
        first_clip_xs.append((x1, y1, x2, y2, org_fid, interpolated))
        # Inserting clipped cross sections to spatial index
        feat = QgsFeature()
        feat.setFeatureId(org_fid)
        feat.setGeometry(geom)
        allfeatures[org_fid] = feat
        index.insertFeature(feat)
        previous[org_fid] = geom

    # Clipping interpolated cross sections to original one and between each other
    previous.clear()
    second_clip_xs = []
    for xs in first_clip_xs:
        x1, y1, x2, y2, org_fid, interpolated = xs
        if interpolated == 0:
            second_clip_xs.append(xs)
            continue

        geom = QgsGeometry.fromPolyline([QgsPoint(x1, y1), QgsPoint(x2, y2)])
        for fid in index.intersects(geom.boundingBox()):
            f = allfeatures[fid]
            fgeom = f.geometry()
            if fgeom.intersects(geom):
                end = geom.intersection(fgeom).asPoint()
                x2, y2 = end.x(), end.y()
                geom = QgsGeometry.fromPolyline([QgsPoint(x1, y1), QgsPoint(x2, y2)])
        for key, prev_geom in previous.items():
            cross = geom.intersects(prev_geom)
            if cross is False:
                previous.popitem(last=False)
            else:
                geom.splitGeometry(prev_geom.asPolyline(), 0)
        previous[org_fid] = geom
        end = geom.asPolyline()[-1]
        x2, y2 = end.x(), end.y()
        second_clip_xs.append((x1, y1, x2, y2, org_fid, interpolated))
    return second_clip_xs


def schematize_1d_area(gutils, cell_size, domain_lyr, centerline_lyr, xs_lyr):
    """
    Schematizing 1D area.
    """
    del_left_sql = '''DELETE FROM chan WHERE center_line_fid IS NOT NULL;'''
    insert_left_sql = '''
        INSERT INTO chan (geom, center_line_fid) VALUES (AsGPB(ST_GeomFromText('LINESTRING({0})')), ?)'''
    del_right_sql = '''DELETE FROM user_rbank WHERE center_line_fid IS NOT NULL;'''
    insert_right_sql = '''
        INSERT INTO user_rbank (geom, center_line_fid) VALUES (AsGPB(ST_GeomFromText('LINESTRING({0})')), ?)'''
    del_chan = 'DELETE FROM chan_elems;'
    insert_chan = '''
        INSERT INTO chan_elems (geom, fid, rbankgrid, seg_fid, nr_in_seg, user_xs_fid, interpolated) VALUES
        (AsGPB(ST_GeomFromText('LINESTRING({0} {1}, {2} {3})')),?,?,?,?,?,?);'''
    gutils.execute(del_left_sql)
    gutils.execute(del_right_sql)
    gutils.execute(del_chan)
    x_offset, y_offset = calculate_offset(gutils, cell_size)
    # Creating spatial index on domain polygons and finding proper one for each river center line
    dom_feats, dom_index = spatial_index(domain_lyr.getFeatures())
    feat2 = None
    for feat1 in centerline_lyr.getFeatures():
        center_fid = feat1.id()
        center_geom = feat1.geometry()
        center_point = center_geom.interpolate(center_geom.length() * 0.5)
        for fid in dom_index.intersects(center_point.boundingBox()):
            f = dom_feats[fid]
            if f.geometry().contains(center_point):
                feat2 = f
                break
        # Getting trimmed and sorted cross section, left and right edge
        xs_features = xs_lyr.getFeatures()
        left_line, right_line, sorted_xs = bank_lines(feat1, feat2, xs_features)
        # Schematizing left and right bank line and writing it into the geopackage
        cursor = gutils.con.cursor()
        left_segment = schematize_points(left_line.asPolyline(), cell_size, x_offset, y_offset)
        right_segment = schematize_points(right_line.asPolyline(), cell_size, x_offset, y_offset)
        seen = set()
        vertices = ','.join(('{0} {1}'.format(*xy) for xy in left_segment if xy not in seen and not seen.add(xy)))
        cursor.execute(insert_left_sql.format(vertices), (center_fid,))
        seen.clear()
        vertices = ','.join(('{0} {1}'.format(*xy) for xy in right_segment if xy not in seen and not seen.add(xy)))
        cursor.execute(insert_right_sql.format(vertices), (center_fid,))
        gutils.con.commit()
        # Finding left and right crossing points along with cross sections fids
        fids, left_points, right_points = bank_stations(sorted_xs, left_line, right_line)
        # Interpolation of cross sections
        left_seg_points = [QgsPoint(*xy) for xy in left_segment]
        left_nodes = closest_nodes(left_seg_points, left_points)
        inter_xs = interpolate_xs(left_seg_points, left_nodes, right_points, fids)
        schema_xs = tuple(schematize_xs(inter_xs, cell_size, x_offset, y_offset))
        clipped_xs = clip_schema_xs(schema_xs)
        sqls = []
        for i, (x1, y1, x2, y2, org_fid, interpolated) in enumerate(clipped_xs, 1):
            try:
                lbankgrid = grid_on_point(gutils, x1, y1)
                rbankgrid = grid_on_point(gutils, x2, y2)
            except Exception as e:
                gutils.uc.log_info(traceback.format_exc())
                continue
            vals = (lbankgrid, rbankgrid, center_fid, i, org_fid, interpolated)
            sqls.append((insert_chan.format(x1, y1, x2, y2), vals))
        cursor = gutils.con.cursor()
        for qry, vals in sqls:
            cursor.execute(qry, vals)
        gutils.con.commit()
    update_1d_area(gutils)
    update_xs_type(gutils)
    update_rbank(gutils)


def grid_on_point(gutils, x, y):
    """
    Getting fid of grid which contains given point.
    """
    qry = '''
    SELECT g.fid
    FROM grid AS g
    WHERE g.ROWID IN (
        SELECT id FROM rtree_grid_geom
        WHERE
            {0} <= maxx AND
            {0} >= minx AND
            {1} <= maxy AND
            {1} >= miny)
    AND
        ST_Intersects(GeomFromGPB(g.geom), ST_GeomFromText('POINT({0} {1})'));
    '''
    qry = qry.format(x, y)
    gid = gutils.execute(qry).fetchone()[0]
    return gid


def update_xs_type(gutils):
    """Updating parameters values specific for each cross section type."""
    gutils.clear_tables('chan_n', 'chan_r', 'chan_t', 'chan_v')
    chan_n = '''INSERT INTO chan_n (elem_fid) VALUES (?);'''
    chan_r = '''INSERT INTO chan_r (elem_fid) VALUES (?);'''
    chan_t = '''INSERT INTO chan_t (elem_fid) VALUES (?);'''
    chan_v = '''INSERT INTO chan_v (elem_fid) VALUES (?);'''
    xs_sql = '''SELECT fid, type FROM chan_elems;'''
    cross_sections = gutils.execute(xs_sql).fetchall()
    cur = gutils.con.cursor()
    for fid, typ in cross_sections:
        if typ == 'N':
            cur.execute(chan_n, (fid,))
        elif typ == 'R':
            cur.execute(chan_r, (fid,))
        elif typ == 'T':
            cur.execute(chan_t, (fid,))
        elif typ == 'V':
            cur.execute(chan_v, (fid,))
        else:
            pass
    gutils.con.commit()


def update_1d_area(gutils):
    """
    Assigning properties from user layers.
    """
    update_chan = '''
    UPDATE chan
    SET
        name = (SELECT name FROM user_centerline WHERE fid = chan.center_line_fid),
        depinitial = (SELECT depinitial FROM user_centerline WHERE fid = chan.center_line_fid),
        froudc = (SELECT froudc FROM user_centerline WHERE fid = chan.center_line_fid),
        roughadj = (SELECT roughadj FROM user_centerline WHERE fid = chan.center_line_fid),
        isedn = (SELECT isedn FROM user_centerline WHERE fid = chan.center_line_fid),
        notes = (SELECT notes FROM user_centerline WHERE fid = chan.center_line_fid);
    '''
    update_chan_elems = '''
    UPDATE chan_elems
    SET
        fcn = (SELECT fcn FROM user_xsections WHERE fid = chan_elems.user_xs_fid),
        type = (SELECT type FROM user_xsections WHERE fid = chan_elems.user_xs_fid),
        notes = (SELECT notes FROM user_xsections WHERE fid = chan_elems.user_xs_fid);
    '''
    update_xlen = '''
    UPDATE chan_elems
    SET
        xlen = (
            SELECT round(ST_Length(ST_Intersection(GeomFromGPB(g.geom), GeomFromGPB(l.geom))), 3)
            FROM grid AS g, chan AS l
            WHERE g.fid = chan_elems.fid AND l.center_line_fid = chan_elems.seg_fid
            );
    '''

    gutils.execute(update_chan)
    gutils.execute(update_chan_elems)
    gutils.execute(update_xlen)


def update_rbank(gutils):
    """
    Create right bank lines
    """
    del_qry = 'DELETE FROM rbank;'
    gutils.execute(del_qry)
    qry = '''
    INSERT INTO rbank (chan_seg_fid, geom)
    SELECT c.fid, AsGPB(MakeLine(centroid(CastAutomagic(g.geom)))) as geom
    FROM
        chan as c,
        (SELECT * FROM  chan_elems ORDER BY seg_fid, nr_in_seg) as ce, -- sorting the chan elems post aggregation doesn't work so we need to sort the before
        grid as g
    WHERE
        c.fid = ce.seg_fid AND
        ce.seg_fid = c.fid AND
        g.fid = ce.rbankgrid
    GROUP BY c.fid;
    '''
    gutils.execute(qry)
