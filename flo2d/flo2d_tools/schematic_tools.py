# -*- coding: utf-8 -*-
import math
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import time
import traceback
from collections import OrderedDict, defaultdict
from math import pi, sqrt
from operator import itemgetter

import numpy as np
from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsVector,
    QgsWkbTypes,
)
from qgis.PyQt.QtWidgets import QApplication

from ..geopackage_utils import GeoPackageUtils
from .grid_tools import (
    buildCellIDNPArray,
    fid_from_grid,
    fid_from_grid_features,
    get_adjacent_cell_elevation,
    spatial_index,
)


# Levees tools
def get_intervals(line_feature, point_features, col_value, buffer_size):
    """
    Function which calculates intervals and assigning values based on intersection between line and snapped points.
    Points are selected by line buffer and filtered by the distance from the line feature.
    """
    lgeom = line_feature.geometry()
    tot_len = lgeom.length()
    buf = lgeom.buffer(buffer_size, 5)
    positions = {}
    for feat in point_features:
        pnt = feat.geometry()
        if buf.contains(pnt):
            pass
        else:
            continue
        pos = lgeom.lineLocatePoint(pnt) / tot_len
        val = feat[col_value]
        closest = lgeom.distance(pnt)
        if pos not in positions or closest < positions[pos][-1]:
            list(positions.values())
            positions[pos] = (pos, val, closest)
        else:
            pass
    snapped = (i[:-1] for i in sorted(list(positions.values()), key=itemgetter(0)))
    intervals = []
    try:
        start_distance, start_value = next(snapped)
        end_distance, end_value = next(snapped)
        while True:
            delta_distance = end_distance - start_distance
            delta_value = end_value - start_value
            interval = (
                start_distance,
                end_distance,
                delta_distance,
                start_value,
                end_value,
                delta_value,
            )
            intervals.append(interval)
            start_distance, start_value = end_distance, end_value
            end_distance, end_value = next(snapped)
    except StopIteration:
        return intervals


def interpolate_along_line(line_feature, sampling_features, intervals, id_col="fid", join_col="user_line_fid"):
    """
    Generator for interpolating values of sampling features centroids snapped to interpolation line.
    Line intervals list needs to be calculated first and derived as a generator parameter.
    """
    start, end = intervals[0], intervals[-1]
    lgeom = line_feature.geometry()
    lid = line_feature[id_col]
    tot_len = lgeom.length()
    sc = [
        (lgeom.lineLocatePoint(f.geometry().centroid()) / tot_len, f[id_col])
        for f in sampling_features
        if f[join_col] == lid
    ]
    sc.sort()
    inter_iter = iter(intervals)
    snapped_iter = iter(sc)
    try:
        (
            start_distance,
            end_distance,
            delta_distance,
            start_value,
            end_value,
            delta_value,
        ) = next(inter_iter)
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
                (
                    start_distance,
                    end_distance,
                    delta_distance,
                    start_value,
                    end_value,
                    delta_value,
                ) = next(inter_iter)
                continue
            position, fid = next(snapped_iter)
    except StopIteration:
        return


def polys2levees(
    line_feature,
    poly_lyr,
    levees_lyr,
    value_col,
    correct_val,
    id_col="fid",
    join_col="user_line_fid",
):
    """
    Generator for assigning elevation values from polygons to levees.
    Levee sides centroids are snapped to the user levee line feature and next tested for intersecting with polygons.
    """
    lgeom = line_feature.geometry()
    lid = line_feature[id_col]
    allfeatures, index = spatial_index(poly_lyr)
    fids = index.intersects(lgeom.boundingBox())
    sel_polys = [allfeatures[fid] for fid in fids if allfeatures[fid].geometry().intersects(lgeom)]
    for feat in levees_lyr.getFeatures():
        if feat[join_col] == lid:
            pass
        else:
            continue
        levcrest = feat["levcrest"]
        center = feat.geometry().centroid()
        pos = lgeom.lineLocatePoint(center)
        pnt = lgeom.interpolate(pos)
        for poly in sel_polys:
            if poly.geometry().contains(pnt):
                abs_val, cor = poly[value_col], poly[correct_val]
                if abs_val and cor:
                    poly_val = abs_val + cor
                elif abs_val and not cor:
                    poly_val = abs_val
                elif not abs_val and cor:
                    poly_val = cor + levcrest
                else:
                    continue
                yield (poly_val, feat[id_col])
                break
            else:
                pass


def levee_grid_isect_pts(levee_fid, grid_fid, levee_lyr, grid_lyr, with_centroid=True):
    lfeat = next(levee_lyr.getFeatures(QgsFeatureRequest(levee_fid)))
    gfeat = next(grid_lyr.getFeatures(QgsFeatureRequest(grid_fid)))
    grid_centroid = gfeat.geometry().centroid().asPoint()
    lg_isect = gfeat.geometry().intersection(lfeat.geometry())
    pts = []

    if lg_isect is None:
        return None

    if lg_isect.type() == QgsWkbTypes.PointGeometry:
        return None

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


def generate_schematic_levees(gutils, levee_lyr, grid_lyr):
    try:
        # octagon nodes to sides map
        octagon_levee_dirs = {0: 1, 1: 5, 2: 2, 3: 6, 4: 3, 5: 7, 6: 4, 7: 8}
        levee_dir_pts = {
            1: (
                lambda x, y, square_half, octa_half: (
                    x - octa_half,
                    y + square_half,
                    x + octa_half,
                    y + square_half,
                )
            ),
            2: (
                lambda x, y, square_half, octa_half: (
                    x + square_half,
                    y + octa_half,
                    x + square_half,
                    y - octa_half,
                )
            ),
            3: (
                lambda x, y, square_half, octa_half: (
                    x + octa_half,
                    y - square_half,
                    x - octa_half,
                    y - square_half,
                )
            ),
            4: (
                lambda x, y, square_half, octa_half: (
                    x - square_half,
                    y - octa_half,
                    x - square_half,
                    y + octa_half,
                )
            ),
            5: (
                lambda x, y, square_half, octa_half: (
                    x + octa_half,
                    y + square_half,
                    x + square_half,
                    y + octa_half,
                )
            ),
            6: (
                lambda x, y, square_half, octa_half: (
                    x + square_half,
                    y - octa_half,
                    x + octa_half,
                    y - square_half,
                )
            ),
            7: (
                lambda x, y, square_half, octa_half: (
                    x - octa_half,
                    y - square_half,
                    x - square_half,
                    y - octa_half,
                )
            ),
            8: (
                lambda x, y, square_half, octa_half: (
                    x - square_half,
                    y + octa_half,
                    x - octa_half,
                    y + square_half,
                )
            ),
        }

        # lid_gid_elev = fid_from_grid(gutils, "user_levee_lines", None, False, False, "elevation")
        # print (lid_gid_elev[0])
        # get user levee lines features
        print("Deleting existing schematized levee and levee failure elements")
        del_levees_sql = """DELETE FROM levee_data  WHERE user_line_fid IS NOT NULL;"""
        del_levee_failures_sql = """DELETE FROM levee_failure;"""
        gutils.con.execute(del_levees_sql)
        gutils.con.execute(del_levee_failures_sql)
        gutils.con.commit()
        print("Intersecting levee elements with grid")

        for lid_gid_elev, regionReq in fid_from_grid_features(
            gutils, grid_lyr, levee_lyr
        ):  # "user_levee_lines", None, False, False, "elevation")
            # print (lid_gid_elev[0])
            cell_size = float(gutils.get_cont_par("CELLSIZE"))
            scale = 0.9
            # square half
            sh = cell_size * 0.5 * scale
            # octagon half
            oh = sh / 2.414
            schem_lines = levee_schematic(lid_gid_elev, levee_lyr, grid_lyr)

            ins_levees_sql = """INSERT INTO levee_data (grid_fid, ldir, levcrest, user_line_fid, geom)
                         VALUES (?,?,?,?, AsGPB(ST_GeomFromText(?)));"""

            levee_failure_qry = """SELECT failevel, failtime, levbase, failwidthmax, failrate, failwidrate
                                    FROM levee_failure 
                                    WHERE grid_fid = ?"""

            ins_levees_failure_sql = """INSERT INTO levee_failure (grid_fid, lfaildir, failevel, failtime,
                                                              levbase, failwidthmax, failrate, failwidrate)
                                         VALUES (?,?,?,?,?,?,?,?);"""

            select_user_levees_qry = """SELECT failElev, failDepth, failDuration, failBaseElev, failMaxWidth, 
                                                            failVRate, failHRate, elev, correction
                                FROM user_levee_lines 
                                WHERE fid = ?"""

            # Create levee segments for distinct levee directions in each grid element
            grid_levee_seg = {}
            data = []
            fail_data = []
            for gid, gdata in schem_lines.items():
                elev = gdata["elev"]
                grid_levee_seg[gid] = {}
                grid_levee_seg[gid]["sides"] = {}
                grid_levee_seg[gid]["centroid"] = gdata["centroid"]
                for lid, sides in gdata["lines"].items():
                    if sides:
                        for side in sides:
                            if side not in list(grid_levee_seg[gid]["sides"].keys()):
                                side_elev = elev
                                grid_levee_seg[gid]["sides"][side] = lid
                                ldir = octagon_levee_dirs[side]
                                c = gdata["centroid"]

                                user_levees_data = gutils.con.execute(select_user_levees_qry, (lid,)).fetchone()
                                if user_levees_data:
                                    if not all(v == 0 for v in user_levees_data):
                                        if not user_levees_data[0] == 0.0:
                                            # failElev selected, use it.
                                            fail_data.append(
                                                (
                                                    gid,
                                                    ldir,
                                                    user_levees_data[0],
                                                    user_levees_data[2],
                                                    user_levees_data[3],
                                                    user_levees_data[4],
                                                    user_levees_data[5],
                                                    user_levees_data[6],
                                                )
                                            )
                                        elif not user_levees_data[1] == 0.0:
                                            # failDepth selected, use adjacent cell elevations to calculate fail elevation.

                                            (
                                                adj_cell,
                                                adj_elev,
                                            ) = get_adjacent_cell_elevation(gutils, grid_lyr, gid, ldir, cell_size)
                                            grid_elev = gutils.grid_value(gid, "elevation")
                                            max_elev = max(adj_elev, grid_elev)

                                            fail_data.append(
                                                (
                                                    gid,
                                                    ldir,
                                                    max_elev + user_levees_data[1],
                                                    user_levees_data[2],
                                                    user_levees_data[3],
                                                    user_levees_data[4],
                                                    user_levees_data[5],
                                                    user_levees_data[6],
                                                )
                                            )
                                        else:  # do not set failure data for this direction.
                                            pass

                                        if user_levees_data[7] is None:  # crest elevation in user levees not defined
                                            (
                                                adj_cell,
                                                adj_elev,
                                            ) = get_adjacent_cell_elevation(gutils, grid_lyr, gid, ldir, cell_size)
                                            side_elev = max(adj_elev, elev)

                                data.append(
                                    (
                                        gid,
                                        ldir,
                                        side_elev,
                                        lid,
                                        "LINESTRING({0} {1}, {2} {3})".format(
                                            *levee_dir_pts[ldir](c.x(), c.y(), sh, oh)
                                        ),
                                    )
                                )

            gutils.con.executemany(ins_levees_sql, data)

            gutils.con.executemany(ins_levees_failure_sql, fail_data)

            gutils.con.commit()
            yield (len(schem_lines), len(data), len(fail_data), regionReq)

        # return len(schem_lines), len(data), len(fail_data)
    except Exception as e:
        raise e
        # self.uc.show_error("ERROR 291219.0428: Error while creating schematic levees octagons!.\n", e)


def delete_redundant_levee_directions_np(gutils, cellIDNumpyArray=None):
    # create a numpy array of the levee segments with a float in each
    # to limit memory, do 2 (opposing directions) at a time
    # shift the NP arrays accordingly to look for conflicts and then delete segments as needed

    retVals = []
    nullVal = -999.0

    if cellIDNumpyArray is None:
        cellIDNumpyArray, xVals, yVals = buildCellIDNPArray(gutils)
    starttime = time.time()
    # print (cellIDNumpyArray)
    # list of opposing levee directions

    oppositeLeveeDirections = [
        [1, 3],
        [2, 4],
        [5, 7],
        [6, 8],
    ]

    rollOrientations = [
        # row roll, col roll
        [1, 0],  # roll north to south
        [0, -1],  # roll east to west
        [1, -1],  # roll northeast to southwest
        [-1, -1],  # roll southeast to northwest
    ]
    # use to find levee cell ids in cellid array in loop - no need to generate through each pass
    flatID = cellIDNumpyArray.flatten()
    idssorted = np.argsort(flatID)

    # make a 2 layer deep array for comparing levee elevations
    for n, dirPair in enumerate(oppositeLeveeDirections):
        print("Processing direction pair: %s" % str(dirPair))

        leveeArray = np.zeros((cellIDNumpyArray.shape[0] + 2, cellIDNumpyArray.shape[1] + 2, 2), dtype=int) + int(
            nullVal
        )
        # assign elevations for the directions of interest
        dir1 = dirPair[0]
        dir2 = dirPair[1]

        levees_qry = "SELECT grid_fid, ldir, levcrest FROM levee_data  WHERE ldir = ? or ldir = ? ORDER BY grid_fid"
        levees = gutils.execute(levees_qry, (dir1, dir2)).fetchall()

        dir1List = [
            (levee[0], levee[2]) for levee in levees if levee[1] == dir1
        ]  # get cellid and crest elevation for dir1 elements
        dir2List = [
            (levee[0], levee[2]) for levee in levees if levee[1] == dir2
        ]  # get cellid and crest elevation for dir1 elements
        dir1List = np.array(dir1List, dtype=float)
        dir2List = np.array(dir2List, dtype=float)

        # assign dir lists to leveeArray based upon the cellID array
        # get the indices for the levee element cellIDs by finding where they fall in the sorted list
        maskdir1 = np.zeros(flatID.shape, dtype=int) + int(nullVal)
        if len(dir1List) != 0:
            dir1pos = np.searchsorted(flatID[idssorted], dir1List[:, 0])
            dir1indices = idssorted[dir1pos]
            maskdir1[dir1indices] = dir1List[:, 0]  # set assigned ids
            del dir1pos, dir1indices

        # now pull their indices in the actual list
        leveeArray[1:-1, 1:-1, 0] = np.reshape(maskdir1, (cellIDNumpyArray.shape[0], cellIDNumpyArray.shape[1]))
        del maskdir1

        maskdir2 = np.zeros(flatID.shape, dtype=int) + int(nullVal)
        if len(dir2List) != 0:
            dir2pos = np.searchsorted(flatID[idssorted], dir2List[:, 0])
            dir2indices = idssorted[dir2pos]
            maskdir2[dir2indices] = dir2List[:, 0]  # set assigned ids
            del dir2pos, dir2indices

        leveeArray[1:-1, 1:-1, 1] = np.reshape(maskdir2, (cellIDNumpyArray.shape[0], cellIDNumpyArray.shape[1]))
        del maskdir2

        # roll the bottom array, based upon direction and look for counts > 1
        rolls = rollOrientations[n]
        if rolls[0] != 0:
            leveeArray[:, :, 1] = np.roll(leveeArray[:, :, 1], rolls[0], axis=0)
        if rolls[1] != 0:
            leveeArray[:, :, 1] = np.roll(leveeArray[:, :, 1], rolls[1], axis=1)
        # for counts > 1, keep the higher elev and delete the lower
        logicArray = leveeArray != -999.0
        counter = np.sum(logicArray, axis=2)
        del logicArray
        conflicts = counter == 2
        del counter
        print("%s redundant levee elements founds" % np.sum(conflicts))

        # based upon which levee element has the lower elevation
        if np.sum(conflicts) > 0:
            conflictIDs = leveeArray[conflicts]
            # print ("Conflict IDs Shape: %s" % str(conflictIDs.shape))
            # compare elevations using the conflict id sets - if the elevation is greater in one, keep it and flag the other for deletion
            dir1ConflictIDs = conflictIDs[:, 0]  # get a 1d array of the ids
            dir2ConflictIDs = conflictIDs[:, 1]  # get a 1d array of the ids

            # dir1 is in ascending order
            dir1Elevs = dir1List[np.searchsorted(dir1List[:, 0], dir1ConflictIDs), 1]
            dir2Elevs = dir2List[np.searchsorted(dir2List[:, 0], dir2ConflictIDs), 1]

            dir1ToDelete = dir1ConflictIDs[dir1Elevs < dir2Elevs]
            dir2ToDelete = dir2ConflictIDs[dir2Elevs <= dir1Elevs]

            # print ("Dir: %s" % dir1)
            # print (dir1ToDelete[0:10])

            # print ("Dir: %s" % dir2)
            # print (dir2ToDelete[0:10])

            retVals.extend([(dir1ToDelete[n], dir1) for n in np.arange(dir1ToDelete.shape[0])])
            retVals.extend([(dir2ToDelete[n], dir2) for n in np.arange(dir2ToDelete.shape[0])])

    delete_qry = "DELETE FROM levee_data WHERE grid_fid = ? AND ldir = ?"
    delete_failure_qry = "DELETE FROM levee_failure WHERE grid_fid = ? and lfaildir = ?;"
    print("%s sec to process duplicates" % (time.time() - starttime))
    return retVals


def delete_levee_directions_duplicates(gutils, levees, grid_lyr):
    """
    Eliminate levee opposite directions. Select the one with highest crest elevation.
    """
    try:
        cell_size = float(gutils.get_cont_par("CELLSIZE"))
        levees_qry = "SELECT grid_fid, ldir, levcrest FROM levee_data ORDER BY grid_fid"
        sel_levee_qry = "SELECT levcrest FROM levee_data WHERE grid_fid = ? AND ldir = ?"
        delete_qry = "DELETE FROM levee_data WHERE grid_fid = ? AND ldir = ?"
        delete_failure_qry = "DELETE FROM levee_failure WHERE grid_fid = ? and lfaildir = ?;"

        levees = gutils.execute(levees_qry).fetchall()
        toDelete = []
        for nextLevee in levees:
            #         for nextLevee in levees.getFeatures():

            #             cell = nextLevee[1]
            #             dir = nextLevee[2]
            #             crest = nextLevee[3]

            cell = nextLevee[0]
            dir = nextLevee[1]
            crest = nextLevee[2]

            oppositeCrest = None
            cellFeat = next(grid_lyr.getFeatures(QgsFeatureRequest(cell)))
            xx, yy = cellFeat.geometry().centroid().asPoint()
            if dir == 1:  # "N"
                # North cell:
                y = yy + cell_size
                x = xx
                dirOpp = 3

            elif dir == 5:  # "NE"
                # NorthEast cell:
                y = yy + cell_size
                x = xx + cell_size
                dirOpp = 7

            elif dir == 2:  # "E"
                # East cell:
                y = yy
                x = xx + cell_size
                dirOpp = 4

            elif dir == 6:  # "SE"
                # SouthEast cell:
                y = yy - cell_size
                x = xx + cell_size
                dirOpp = 8

            elif dir == 3:  # "S"
                # South cell:
                y = yy - cell_size
                x = xx
                dirOpp = 1

            elif dir == 7:  # "SW"
                # SouthWest cell:
                y = yy - cell_size
                x = xx - cell_size
                dirOpp = 5

            elif dir == 4:  # "W"
                # West cell:
                y = yy
                x = xx - cell_size
                dirOpp = 2

            elif dir == 8:  # "NW"
                # NorthWest cell:
                y = yy + cell_size
                x = xx - cell_size
                dirOpp = 6

            else:
                X = -99
                y = -99

            oppositeCell = gutils.grid_on_point(x, y)
            if oppositeCell is not None:
                oppositeCrest = gutils.execute(sel_levee_qry, (oppositeCell, dirOpp)).fetchone()
                if oppositeCrest:
                    if crest < oppositeCrest[0]:
                        toDelete.append((cell, dir))
                    #                         gutils.execute(delete_qry, (cell,dir))

                    elif crest == oppositeCrest[0]:
                        # Arbitrary delete high cell number to avoid duplicate later.
                        if oppositeCell > cell:
                            toDelete.append((oppositeCell, dirOpp))
                        #                            gutils.execute(delete_qry, (oppositeCell,dir))
                        else:
                            toDelete.append((cell, dir))
                    #                            gutils.execute(delete_qry, (oppositeCell,dir))
                    else:
                        toDelete.append((oppositeCell, dirOpp))
        #                         gutils.execute(delete_qry, (oppositeCell,dir))

        toDelete = list(set(toDelete))
        toDelete.sort()
        return toDelete

    except Exception as e:
        QApplication.restoreOverrideCursor()
        raise e
        # self.uc.show_error("ERROR 040620.0648: unable to eliminate duplicate levee directions!\n", e)


# ...............................

# def generate_schematic_levees(gutils, levee_lyr, grid_lyr):
#     # octagon nodes to sides map
#     octagon_levee_dirs = {0: 1, 1: 5, 2: 2, 3: 6, 4: 3, 5: 7, 6: 4, 7: 8}
#     levee_dir_pts = {
#         1: (lambda x, y, square_half, octa_half: (x - octa_half, y + square_half, x + octa_half, y + square_half)),
#         2: (lambda x, y, square_half, octa_half: (x + square_half, y + octa_half, x + square_half, y - octa_half)),
#         3: (lambda x, y, square_half, octa_half: (x + octa_half, y - square_half, x - octa_half, y - square_half)),
#         4: (lambda x, y, square_half, octa_half: (x - square_half, y - octa_half, x - square_half, y + octa_half)),
#         5: (lambda x, y, square_half, octa_half: (x + octa_half, y + square_half, x + square_half, y + octa_half)),
#         6: (lambda x, y, square_half, octa_half: (x + square_half, y - octa_half, x + octa_half, y - square_half)),
#         7: (lambda x, y, square_half, octa_half: (x - octa_half, y - square_half, x - square_half, y - octa_half)),
#         8: (lambda x, y, square_half, octa_half: (x - square_half, y + octa_half, x - octa_half, y + square_half))
#     }
#     lid_gid_elev = fid_from_grid(gutils, 'user_levee_lines', None, False, False, 'elevation')
#     cell_size = float(gutils.get_cont_par('CELLSIZE'))
#     scale = 0.9
#     # square half
#     sh = cell_size * 0.5 * scale
#     # octagon half
#     oh = sh / 2.414
#     schem_lines = levee_schematic(lid_gid_elev, levee_lyr, grid_lyr)
#
#     del_levees_sql = '''DELETE FROM levee_data WHERE user_line_fid IS NOT NULL;'''
#     ins_levees_sql = '''INSERT INTO levee_data (grid_fid, ldir, levcrest, user_line_fid, geom)
#                  VALUES (?,?,?,?, AsGPB(ST_GeomFromText(?)));'''
#     del_levee_failures_sql = '''DELETE FROM levee_failure'''
#
#     # create levee segments for distinct levee directions in each grid element
#     grid_levee_seg = {}
#     data = []
#     for gid, gdata in schem_lines.items():
#         elev = gdata['elev']
#         grid_levee_seg[gid] = {}
#         grid_levee_seg[gid]['sides'] = {}
#         grid_levee_seg[gid]['centroid'] = gdata['centroid']
#         for lid, sides in gdata['lines'].items():
#             for side in sides:
#                 if side not in list(grid_levee_seg[gid]['sides'].keys()):
#                     grid_levee_seg[gid]['sides'][side] = lid
#                     ldir = octagon_levee_dirs[side]
#                     c = gdata['centroid']
#                     data.append((
#                         gid,
#                         ldir,
#                         elev,
#                         lid,
#                         'LINESTRING({0} {1}, {2} {3})'.format(*levee_dir_pts[ldir](c.x(), c.y(), sh, oh))
#                     ))
#     gutils.con.execute(del_levees_sql)
#     gutils.con.execute(del_levee_failures_sql)
#     gutils.con.executemany(ins_levees_sql, data)
#     gutils.con.commit()

# ....................................


def levee_schematic(lid_gid_elev, levee_lyr, grid_lyr):
    try:
        schem_lines = {}
        gids = []
        nv = QgsVector(0, 1)
        # for each line crossing a grid element
        for lid, gid, elev in lid_gid_elev:
            pts_c = levee_grid_isect_pts(lid, gid, levee_lyr, grid_lyr)
            if pts_c is None:
                continue
            pts, c = pts_c
            if gid not in gids:
                schem_lines[gid] = {}
                schem_lines[gid]["lines"] = {}
                schem_lines[gid]["centroid"] = c
                schem_lines[gid]["elev"] = elev
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
            schem_lines[gid]["lines"][lid] = sides
        return schem_lines
    except Exception as e:
        raise e
        # self.uc.show_error("ERROR 030120.0731: Error while creating schematic levees!.\n", e)


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


def schematize_lines(lines, cell_size, offset_x, offset_y, feats_only=False, get_id=False):
    """
    Generator for finding grid centroids coordinates for each schematized line segment.
    Calculations are done using Bresenham's Line Algorithm.

    Wikipedia: Bresenham's line algorithm is an algorithm that determines the points of an n-dimensional raster
    that should be selected in order to form a close approximation to a straight line between two points.
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


def inject_points(line_geom, points):
    """
    Function for inserting points located on line geometry as line vertexes.
    """
    new_line = line_geom.asPolyline()
    iline = iter(line_geom.asPolyline())
    ipoints = iter(points)
    pnt = next(ipoints)
    xy = next(iline)
    distance = line_geom.lineLocatePoint(QgsGeometry.fromPointXY(pnt))
    vdistance = line_geom.lineLocatePoint(QgsGeometry.fromPointXY(xy))
    shift = 0
    index = 0
    try:
        while True:
            if vdistance == distance:
                pnt = next(ipoints)
                xy = next(iline)
                distance = line_geom.lineLocatePoint(QgsGeometry.fromPointXY(pnt))
                vdistance = line_geom.lineLocatePoint(QgsGeometry.fromPointXY(xy))
                index += 1
            elif vdistance < distance:
                xy = next(iline)
                vdistance = line_geom.lineLocatePoint(QgsGeometry.fromPointXY(xy))
                index += 1
            elif vdistance > distance:
                new_line.insert(index + shift, pnt)
                pnt = next(ipoints)
                distance = line_geom.lineLocatePoint(QgsGeometry.fromPointXY(pnt))
                shift += 1
    except StopIteration:
        return new_line


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
    streets_sql = """INSERT INTO streets (fid) VALUES (?);"""
    seg_sql = """INSERT INTO street_seg (geom, str_fid) VALUES (AsGPB(ST_GeomFromText('MULTILINESTRING({0})')), ?)"""
    elems_sql = """INSERT INTO street_elems (seg_fid, istdir) VALUES (?,?)"""
    gpb_part = """({0} {1}, {2} {3})"""
    half_cell = cell_size * 0.5
    gutils.clear_tables("streets", "street_seg", "street_elems")
    functions = {
        1: (lambda x, y, shift: (x, y + shift)),
        2: (lambda x, y, shift: (x + shift, y)),
        3: (lambda x, y, shift: (x, y - shift)),
        4: (lambda x, y, shift: (x - shift, y)),
        5: (lambda x, y, shift: (x + shift, y + shift)),
        6: (lambda x, y, shift: (x + shift, y - shift)),
        7: (lambda x, y, shift: (x - shift, y - shift)),
        8: (lambda x, y, shift: (x - shift, y + shift)),
    }
    x_offset, y_offset = gutils.calculate_offset(cell_size)
    fid_segments = schematize_lines(line_layer, cell_size, x_offset, y_offset, get_id=True)
    cursor = gutils.con.cursor()
    fid_coords = {}
    coords = defaultdict(set)
    # Populating directions within each grid cell
    for fid, grids in fid_segments:
        populate_directions(coords, grids)
        # Assigning user line fid for each grid centroid coordinates
        for xy in coords.keys():
            if xy not in fid_coords:
                fid_coords[xy] = fid
            else:
                continue
        cursor.execute(streets_sql, (fid,))
    for i, (xy, directions) in enumerate(iter(coords.items()), 1):
        x1, y1 = xy
        xy_dir = []
        for d in directions:
            cursor.execute(elems_sql, (i, d))
            xy_dir.append(functions[d](x1, y1, half_cell))
        multiline = ",".join((gpb_part.format(x1, y1, x2, y2) for x2, y2 in xy_dir))
        gpb_insert = seg_sql.format(multiline)
        cursor.execute(gpb_insert, (fid_coords[xy],))
    gutils.con.commit()
    fid_grid = fid_from_grid(gutils, "street_seg", grid_center=True, switch=True)
    grid_sql = """UPDATE street_seg SET igridn = ? WHERE fid = ?;"""
    gutils.execute_many(grid_sql, fid_grid)
    update_streets = """
    UPDATE streets SET
        stname = (SELECT name FROM user_streets WHERE fid = streets.fid),
        notes = (SELECT notes FROM user_streets WHERE fid = streets.fid);"""
    update_street_seg = """
    UPDATE street_seg SET
        depex = (SELECT curb_height FROM user_streets WHERE fid = street_seg.str_fid),
        stman = (SELECT n_value FROM user_streets WHERE fid = street_seg.str_fid),
        elstr = (SELECT elevation FROM user_streets WHERE fid = street_seg.str_fid);"""
    update_street_elems = """
        UPDATE street_elems SET
            widr = (
                    SELECT us.street_width
                    FROM user_streets AS us, street_seg AS seg
                    WHERE us.fid = seg.str_fid AND street_elems.seg_fid = seg.fid);
                    """
    crop_seg_sql = """DELETE FROM street_seg WHERE igridn IS NULL;"""
    crop_elem_sql = """DELETE FROM street_elems WHERE seg_fid NOT IN (SELECT fid FROM street_seg);"""
    gutils.execute(update_streets)
    gutils.execute(update_street_seg)
    gutils.execute(update_street_elems)
    gutils.execute(crop_seg_sql)
    gutils.execute(crop_elem_sql)


def schematize_reservoirs(gutils):
    gutils.clear_tables("reservoirs")
    ins_qry = """INSERT INTO reservoirs (user_res_fid, name, grid_fid, wsel)
                SELECT
                    ur.fid, ur.name, g.fid, ur.wsel
                FROM
                    grid AS g, user_reservoirs AS ur
                WHERE
                    ST_Intersects(CastAutomagic(g.geom), CastAutomagic(ur.geom))
                LIMIT 1;"""
    gutils.execute(ins_qry)


class ChannelsSchematizer(GeoPackageUtils):
    """
    Class for handling 1D Domain schematizing processes.
    """

    def __init__(self, con, iface, lyrs):
        super(ChannelsSchematizer, self).__init__(con, iface)
        self.lyrs = lyrs
        self.cell_size = float(self.get_cont_par("CELLSIZE"))
        self.x_offset, self.y_offset = self.calculate_offset(self.cell_size)

        self.user_lbank_lyr = lyrs.data["user_left_bank"]["qlyr"]
        self.user_rbank_lyr = lyrs.data["user_right_bank"]["qlyr"]
        self.schematized_lbank_lyr = lyrs.data["chan"]["qlyr"]
        self.schematized_rbank_lyr = lyrs.data["rbank"]["qlyr"]
        self.user_xsections_lyr = lyrs.data["user_xsections"]["qlyr"]
        self.schematized_xsections_lyr = lyrs.data["chan_elems"]["qlyr"]

        self.xs_index = None
        self.xsections_feats = None

        self.banks_data = []
        self.update_banks_elev()

    def update_banks_elev(self):
        try:
            sel_qry = """SELECT elevation FROM grid WHERE fid = ?;"""
            update_table = {"T": "user_chan_t", "R": "user_chan_r"}
            elems = {}
            for feat in self.user_xsections_lyr.getFeatures():
                fid = feat["fid"]
                typ = feat["type"]
                if typ not in ["T", "R"]:
                    continue
                line_geom = feat.geometry().asPolyline()
                start = line_geom[0]
                end = line_geom[-1]
                lgid = self.grid_on_point(start.x(), start.y())
                rgid = self.grid_on_point(end.x(), end.y())
                lelev = self.execute(sel_qry, (lgid,)).fetchone()[0]
                relev = self.execute(sel_qry, (rgid,)).fetchone()[0]
                elems[fid] = (lelev, relev, typ)

            update_qry = """UPDATE {0} SET {1} = ? WHERE user_xs_fid = ? AND {1} IS NULL;"""
            for fid, (lelev, relev, typ) in list(elems.items()):
                table = update_table[typ]
                cur = self.con.cursor()
                cur.execute(update_qry.format(table, "bankell"), (lelev, fid))
                cur.execute(update_qry.format(table, "bankelr"), (relev, fid))
            self.con.commit()
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_error(
                "ERROR 080721.1126: Error while updating bank elevations around (left, right) cells: ("
                + str(lgid)
                + ", "
                + str(rgid)
                + ")",
                e,
            )

    def set_xs_features(self):
        """
        Setting features and spatial indexes.
        """
        self.xsections_feats, self.xs_index = spatial_index(self.user_xsections_lyr)

    def get_sorted_xs(self, line_feat):
        """
        Selecting and sorting cross sections for given line.
        """
        line = line_feat.geometry()
        fids = self.xs_index.intersects(line.boundingBox())
        cross_sections = [
            self.xsections_feats[fid] for fid in fids if self.xsections_feats[fid].geometry().intersects(line)
        ]  # Selects cross sections that intersect this channel segment.
        cross_sections.sort(key=lambda cs: line.lineLocatePoint(cs.geometry().nearestPoint(line)))
        return cross_sections

    def create_schematized_channel_segments_aka_left_banks(self):
        """
        Schematizing banks and cross section.
        """
        # Creating spatial index on cross sections and finding proper one for each river center line
        self.set_xs_features()  # Creates self.xsections_feats and self.xs_index of the user cross sections.
        feat_xs = []
        for left_bank_feature in self.user_lbank_lyr.getFeatures():  # For each channel segment.
            # Getting sorted cross section
            line_start = QgsPointXY(left_bank_feature.geometry().vertexAt(0))
            sorted_xs = self.get_sorted_xs(
                left_bank_feature
            )  # Selects XSs than intersect this channel segment, orders them from
            # beginning of segment, checks than there are more than 2 CS, and
            # the first one intersects the line.
            if len(sorted_xs) < 2:
                self.uc.show_warn("WARNING 060319.1633: You need at least 2 cross-sections crossing left bank line!")
                raise Exception

            first_xs = sorted_xs[0]
            xs_start = QgsPointXY(first_xs.geometry().vertexAt(0))

            if self.grid_on_point(line_start.x(), line_start.y()) == self.grid_on_point(xs_start.x(), xs_start.y()):
                feat_xs.append((left_bank_feature, sorted_xs))
            else:
                msg = "WARNING 060319.1617: Left bank line ({}) and first cross-section ({}) must start in the same grid cell, and intersect!"
                msg = msg.format(left_bank_feature.attributes()[1], first_xs.attributes()[3])
                self.uc.show_warn(msg)
                raise Exception

        for (
            feat,
            sorted_xs,
        ) in feat_xs:  # For each channel segment and the XSs that intersect them.
            lbank_fid = feat.id()
            lbank_geom = QgsGeometry.fromPolylineXY(feat.geometry().asPolyline())
            # Getting left edge.
            self.schematize_leftbanks(feat)  # Created schematized geometric 'chan' table, with a polyline of all the
            # centroids of the cells that intersect this channel segment line.
            self.banks_data.append(
                (lbank_fid, lbank_geom, sorted_xs)
            )  # 'banks_data' contains for each channel segment (lbank_fid):
            # the polyline of centroids of cells and the list of XSs that
            # intersect the channel segment.
        self.schematized_lbank_lyr.triggerRepaint()  # Remember to repaint. Will be repainted by QGIS when needed to force the update.

    def create_schematized_rbank_lines_from_user_rbanks_banks(self):
        """
        Schematizing right bank.
        """
        self.clear_tables("rbank")
        for feat in self.user_rbank_lyr.getFeatures():  # For each user right bank segment.
            rbank_fid = feat.id()
            rbank_geom = QgsGeometry.fromPolylineXY(feat.geometry().asPolyline())
            # Getting left edge.
            self.schematize_rightbanks(feat)  # Created schematized geometric 'rbank' table, with a polyline of all the
            # centroids of the cells that intersect this right segment line.

        self.schematized_rbank_lyr.triggerRepaint()  # Remember to repaint. Will be repainted by QGIS when needed to force the update.

    def create_schematized_channels(self):
        """
        Schematizing banks and cross-section.
        """

        nxsecnum = []

        self.set_xs_features()  # Creates self.xsections_feats and self.xs_index of the user cross sections.
        feat_xs = []
        found_right_bank_feature_id = []
        for left_bank_feature in self.user_lbank_lyr.getFeatures():  # For each channel segment.
            # Getting sorted cross section
            sorted_xs = self.get_sorted_xs(
                left_bank_feature
            )  # Selects XSs than intersect this channel segment, orders them from
            # beginning of segment, checks than there are more than 2 CS, and
            # the first one intersects the line.
            if len(sorted_xs) < 2:
                self.uc.show_warn("WARNING 060319.1633: You need at least 2 cross-sections crossing left bank line!")
                raise Exception

            line_start = QgsPointXY(left_bank_feature.geometry().vertexAt(0))
            first_xs = sorted_xs[0]
            xs_start = QgsPointXY(first_xs.geometry().vertexAt(0))

            if self.grid_on_point(line_start.x(), line_start.y()) != self.grid_on_point(xs_start.x(), xs_start.y()):
                msg = "WARNING 060319.1829: Left bank line ({}) and first cross-section ({}) must start in the same grid cell, and intersect!"
                msg = msg.format(left_bank_feature.attributes()[1], first_xs.attributes()[3])
                self.uc.show_warn(msg)
                raise Exception

            # Now search for a right bank segment that intersect same cross sections
            right_bank_feature = QgsFeature()
            for rb in self.user_rbank_lyr.getFeatures():
                if rb.id() in found_right_bank_feature_id:
                    continue
                intersected_cross_section = self.get_sorted_xs(rb)
                # Check if are the same cross sections
                if len(intersected_cross_section) != len(sorted_xs):
                    continue
                is_same_cross_sections = True
                for i in range(0, len(intersected_cross_section) - 1):
                    is_same_cross_sections &= intersected_cross_section[i].id() == sorted_xs[i].id()
                    if not is_same_cross_sections:
                        break

                if is_same_cross_sections:
                    # we've got the good one
                    right_bank_feature = rb
                    right_bank_feature.setAttribute("chan_seg_fid", left_bank_feature.attribute("fid"))
                    found_right_bank_feature_id.append(right_bank_feature.id())
                    break

            if right_bank_feature.isValid():
                line_start = QgsPointXY(right_bank_feature.geometry().vertexAt(0))
                last_index = len(first_xs.geometry().asPolyline()) - 1
                xs_end = QgsPointXY(first_xs.geometry().vertexAt(last_index))

                if self.grid_on_point(line_start.x(), line_start.y()) != self.grid_on_point(xs_end.x(), xs_end.y()):
                    msg = "WARNING 060319.1823: Right bank line ({}) and first cross-section ({}) must start in the same grid cell, and intersect!"
                    msg = msg.format(left_bank_feature.attributes()[1], first_xs.attributes()[3])
                    expression = "{} = '{}'".format('name', first_xs.attributes()[3])
                    features = self.user_xsections_lyr.getFeatures(expression)
                    for feature in features:
                        self.user_xsections_lyr.selectByIds([feature.id()])
                        self.iface.mapCanvas().zoomToSelected(self.user_xsections_lyr)
                        break
                    self.uc.show_warn(msg)
                    self.uc.log_info(msg)
                    raise Exception

            feat_xs.append((left_bank_feature, right_bank_feature, sorted_xs))
            for xs in sorted_xs:
                if xs.attribute("type") == "N":
                    nxsecnum.append(xs.attribute("fid"))

        if len(found_right_bank_feature_id) != self.user_rbank_lyr.featureCount():
            rb_not_used = []
            for rb in self.user_rbank_lyr.getFeatures():
                if rb.id() not in found_right_bank_feature_id:
                    rb_not_used.append(rb.id())
            ids_adjusted = ' - '.join([str(id) for id in rb_not_used])
            message = f"WARNING 060319.1633: The following right bank(s) were not used: \n\n" \
                      f"FID {ids_adjusted}\n\n" \
                      f"Schematize channel will continue but check your user layers."
            self.uc.show_warn(message)
            self.uc.log_info(message)
            self.user_rbank_lyr.selectByIds([rb_not_used[0]])
            self.iface.mapCanvas().zoomToSelected(self.user_rbank_lyr)

        # schematized banks (left bank and right bank if exists and is valid)
        self.clear_tables("chan", "chan_elems", "rbank", "chan_confluences")
        for left_feat, right_feat, sorted_xs in feat_xs:
            left_bank_fid = left_feat.id()
            left_bank_geom = QgsGeometry.fromPolylineXY(left_feat.geometry().asPolyline())
            # before schematized bank, insert point on intersection with cross section
            user_left_bank_positions = self.bank_stations(sorted_xs, left_bank_geom)
            for intersection in user_left_bank_positions:
                (
                    dist,
                    x_y_position,
                    vert_pos,
                    left,
                ) = left_bank_geom.closestSegmentWithContext(intersection)
                left_bank_geom.insertVertex(x_y_position.x(), x_y_position.y(), vert_pos)
            left_feat.setGeometry(left_bank_geom)

            user_right_bank_positions = []
            right_bank_fid = -1
            right_bank_geom = QgsGeometry()
            if right_feat.isValid():
                right_bank_fid = right_feat.attribute("chan_seg_fid")
                right_bank_geom = QgsGeometry.fromPolylineXY(right_feat.geometry().asPolyline())
                # before schematized bank, insert point on intersection with cross section
                user_right_bank_positions = self.bank_stations(sorted_xs, right_bank_geom)
                for intersection in user_right_bank_positions:
                    (
                        dist,
                        x_y_position,
                        vert_pos,
                        left,
                    ) = right_bank_geom.closestSegmentWithContext(intersection)
                    right_bank_geom.insertVertex(x_y_position.x(), x_y_position.y(), vert_pos)
                right_feat.setGeometry(right_bank_geom)

                self.schematize_rightbanks(right_feat)

            self.schematize_leftbanks(left_feat)
            self.banks_data.append(
                (
                    left_bank_fid,
                    left_bank_geom,
                    right_bank_fid,
                    right_bank_geom,
                    sorted_xs,
                    user_left_bank_positions,
                    user_right_bank_positions,
                )
            )

        self.create_schematized_xsections()

        self.schematized_lbank_lyr.triggerRepaint()
        self.schematized_rbank_lyr.triggerRepaint()

        # update nxsecnum in user_chan_n table
        for i in range(0, len(nxsecnum)):
            sql = """UPDATE user_chan_n SET nxsecnum = ? WHERE user_xs_fid = ?;"""
            self.execute(sql, (i + 1, nxsecnum[i]))

    def create_schematized_xsections(self):
        """
        Schematizing cross sections.
        """
        insert_chan = """
        INSERT INTO chan_elems (geom, fid, rbankgrid, seg_fid, nr_in_seg, user_xs_fid, interpolated) VALUES
        (AsGPB(ST_GeomFromText('LINESTRING({0} {1}, {2} {3})')),?,?,?,?,?,?);"""

        cross_section_definitions = []
        for (
            lbank_fid,
            lbank_geom,
            rbank_fid,
            rbank_geom,
            sorted_xs,
            user_left_bank_positions,
            user_right_bank_positions,
        ) in self.banks_data:
            req = QgsFeatureRequest().setFilterExpression('"user_lbank_fid" = {}'.format(lbank_fid))
            left_schematized_feat = next(self.schematized_lbank_lyr.getFeatures(req))
            left_schematized_geometry = left_schematized_feat.geometry()

            # Finding closest points in the schematized left bank
            user_left_bank_nodes = self.closest_nodes(left_schematized_geometry, user_left_bank_positions)

            # make sure the first cross section is connected with the first point of the bank
            user_left_bank_nodes[0] = (
                QgsPointXY(left_schematized_geometry.vertexAt(0)),
                0,
            )

            if rbank_fid >= 0:
                # do the same with right bank
                req = QgsFeatureRequest().setFilterExpression('"chan_seg_fid" = {}'.format(rbank_fid))
                rsegment_feat = next(self.schematized_rbank_lyr.getFeatures(req))
                rsegment_points = rsegment_feat.geometry()
                user_right_bank_nodes = self.closest_nodes(rsegment_points, user_right_bank_positions)

                if len(user_right_bank_nodes) != len(user_left_bank_nodes):
                    # something got wrong...
                    self.uc.show_warn("WARNING 060319.XXXX: Error during schematization")
                    raise Exception

                # create cross sections between banks
                for i in range(len(user_left_bank_nodes) - 1):
                    start_right_node = user_right_bank_nodes[i]
                    start_right_position = start_right_node[0]
                    start_right_node_idx = start_right_node[1]
                    start_left_node = user_left_bank_nodes[i]
                    start_left_position = start_left_node[0]
                    start_left_node_idx = start_left_node[1]

                    end_right_node = user_right_bank_nodes[i + 1]
                    end_right_node_idx = end_right_node[1]
                    end_left_node = user_left_bank_nodes[i + 1]
                    end_left_node_idx = end_left_node[1]

                    xs = sorted_xs[i]
                    vals = (
                        start_left_position,
                        start_right_position,
                        lbank_fid,
                        start_left_node_idx + 1,
                        xs.id(),
                        False,
                    )
                    cross_section_definitions.append(vals)

                    left_bank_points = left_schematized_geometry.asPolyline()
                    right_bank_points = rsegment_points.asPolyline()
                    idx_count_left = end_left_node_idx - start_left_node_idx
                    idx_count_right = end_right_node_idx - start_right_node_idx

                    if idx_count_left <= idx_count_right:
                        idx_step_left = 1.0
                        idx_step_right = idx_count_right / idx_count_left
                    else:
                        idx_step_left = idx_count_left / idx_count_right
                        idx_step_right = 1.0

                    idx_right = 1

                    right_bank_interpolate_xs = start_right_position

                    for index in range(1, idx_count_left):
                        idx_left = index + start_left_node_idx
                        if idx_count_left <= idx_count_right:
                            idx_float_right = idx_step_right * index + start_right_node_idx
                            right_bank_interpolate_xs = right_bank_points[int(idx_float_right)]
                            left_bank_interpolate_xs = left_bank_points[idx_left]
                            vals = (
                                left_bank_interpolate_xs,
                                right_bank_interpolate_xs,
                                lbank_fid,
                                idx_left + 1,
                                xs.id(),
                                True,
                            )
                            cross_section_definitions.append(vals)
                        else:
                            idx_float_left = idx_step_left * idx_right + start_left_node_idx
                            left_bank_interpolate_xs = left_bank_points[idx_left]
                            if int(idx_float_left) == idx_left:
                                right_bank_interpolate_xs = right_bank_points[idx_right + start_right_node_idx]
                                vals = (
                                    left_bank_interpolate_xs,
                                    right_bank_interpolate_xs,
                                    lbank_fid,
                                    idx_left + 1,
                                    xs.id(),
                                    True,
                                )
                                cross_section_definitions.append(vals)
                                idx_right = idx_right + 1
                            else:
                                vals = (
                                    left_bank_interpolate_xs,
                                    right_bank_interpolate_xs,
                                    lbank_fid,
                                    idx_left + 1,
                                    xs.id(),
                                    True,
                                )
                                cross_section_definitions.append(vals)

                end_right_node = user_right_bank_nodes[len(user_left_bank_nodes) - 1]
                end_right_position = end_right_node[0]
                end_left_node = user_left_bank_nodes[len(user_left_bank_nodes) - 1]
                end_left_position = end_left_node[0]
                end_left_node_idx = end_left_node[1]
                xs = sorted_xs[len(sorted_xs) - 1]
                vals = (
                    end_left_position,
                    end_right_position,
                    lbank_fid,
                    end_left_node_idx + 1,
                    xs.id(),
                    False,
                )
                cross_section_definitions.append(vals)

            else:  # right bank is not valid, only consider left bank to define channel
                for i in range(len(user_left_bank_nodes) - 1):
                    start_left_node = user_left_bank_nodes[i]
                    start_left_position = start_left_node[0]
                    start_left_node_idx = start_left_node[1]

                    end_left_node = user_left_bank_nodes[i + 1]
                    end_left_position = end_left_node[0]
                    end_left_node_idx = end_left_node[1]

                    xs = sorted_xs[i]
                    vals = (
                        start_left_position,
                        QgsPointXY(),
                        lbank_fid,
                        start_left_node_idx + 1,
                        xs.id(),
                        False,
                    )
                    cross_section_definitions.append(vals)

                    idx_left = start_left_node_idx + 1
                    left_bank_points = left_schematized_geometry.asPolyline()
                    while idx_left < end_left_node_idx:
                        left_bank_interpolate_xs = left_bank_points[idx_left]
                        vals = (
                            left_bank_interpolate_xs,
                            QgsPointXY(),
                            lbank_fid,
                            idx_left,
                            xs.id() + 1,
                            True,
                        )
                        cross_section_definitions.append(vals)
                        idx_left = idx_left + 1

                end_left_node = user_left_bank_nodes[len(user_left_bank_nodes) - 1]
                end_left_position = end_left_node[0]
                end_left_node_idx = end_left_node[1]
                xs = sorted_xs[len(sorted_xs) - 1]
                vals = (
                    end_left_position,
                    QgsPointXY(),
                    lbank_fid,
                    end_left_node_idx + 1,
                    xs.id(),
                    False,
                )
                cross_section_definitions.append(vals)

        # Saving schematized and interpolated cross sections
        sqls = []
        ordered = []
        lbankgrids = []
        rbankgrids = []
        prev_node_pos = QgsPointXY()  # direction of the previous node used to give direction of xs with no right bank
        for i in range(len(cross_section_definitions)):
            (
                pt1,
                pt2,
                lbank_fid,
                nr_in_seg,
                xs_fid,
                interpolated,
            ) = cross_section_definitions[i]
            try:
                lbankgrid = self.grid_on_point(pt1.x(), pt1.y())
                if not pt2.isEmpty():
                    rbankgrid = self.grid_on_point(pt2.x(), pt2.y())
                else:
                    rbankgrid = 0
            except Exception as e:
                self.uc.log_info(traceback.format_exc())
                continue

            lbankgrids.append(lbankgrid)
            rbankgrids.append(rbankgrid)

            if lbankgrid == rbankgrid:
                rbankgrid = 0

            vals = (lbankgrid, rbankgrid, lbank_fid, nr_in_seg, xs_fid, interpolated)

            if rbankgrid != 0:
                geom_pt1 = pt1
                geom_pt2 = pt2
            else:
                if nr_in_seg != 1:  # not the first cross section of the segment
                    if pt1.x() > prev_node_pos.x():
                        dy = self.cell_size / 2
                    elif pt1.x() == prev_node_pos.x():
                        dy = 0
                    else:
                        dy = -self.cell_size / 2

                    if pt1.y() > prev_node_pos.y():
                        dx = self.cell_size / 2
                    elif pt1.y() == prev_node_pos.y():
                        dx = 0
                    else:
                        dx = -self.cell_size / 2
                else:
                    next_definition = cross_section_definitions[i + 1]
                    next_point = next_definition[0]
                    if next_point.x() > pt1.x():
                        dy = self.cell_size / 2
                    elif next_point.x() == pt1.x():
                        dy = 0
                    else:
                        dy = -self.cell_size / 2

                    if next_point.y() > pt1.y():
                        dx = self.cell_size / 2
                    elif next_point.y() == pt1.y():
                        dx = 0
                    else:
                        dx = -self.cell_size / 2

                geom_pt1 = QgsPointXY(pt1.x() - dx, pt1.y() + dy)
                geom_pt2 = QgsPointXY(pt1.x() + dx, pt1.y() - dy)

            x1, y1 = pt1.x(), pt1.y()
            x2, y2 = pt2.x(), pt2.y()

            dx = x2 - x1
            dy = y2 - y1
            L = math.hypot(dx, dy)

            seen = set()

            def add_grid_id(gid):
                if gid and gid not in seen:
                    seen.add(gid)
                    ordered.append(gid)

            if L == 0:
                try:
                    add_grid_id(self.grid_on_point(x1, y1))
                except Exception:
                    pass

            x1, y1 = pt1.x(), pt1.y()
            x2, y2 = pt2.x(), pt2.y()

            dx = x2 - x1
            dy = y2 - y1
            L = math.hypot(dx, dy)

            seen = set()

            def add_grid_id(gid):
                if gid and gid not in seen:
                    seen.add(gid)
                    ordered.append(gid)

            if L == 0:
                # no “between” cells when endpoints are excluded
                pass
            else:
                # Step along the segment only (no perpendicular sweep)
                step = max(self.cell_size / 4.0, 1e-9)  # finer than 1/2 cell to avoid skips
                n_steps = max(1, int(math.ceil(L / step)))

                for k in range(1, n_steps):  # 1..n_steps-1 → excludes endpoints
                    t = k / n_steps
                    sx = x1 + t * dx
                    sy = y1 + t * dy
                    try:
                        gid = self.grid_on_point(sx, sy)
                        add_grid_id(gid)
                    except Exception:
                        continue

                # tiny overreach along the segment direction to catch fence sitters (still excludes endpoints)
                tx, ty = dx / L, dy / L
                eps = 1e-6 * self.cell_size
                for ex, ey in ((x1 + eps * tx, y1 + eps * ty), (x2 - eps * tx, y2 - eps * ty)):
                    try:
                        gid = self.grid_on_point(ex, ey)
                        add_grid_id(gid)
                    except Exception:
                        pass



            prev_node_pos = pt1
            sqls.append(
                (
                    insert_chan.format(geom_pt1.x(), geom_pt1.y(), geom_pt2.x(), geom_pt2.y()),
                    vals,
                )
            )

        ordered = [g for g in ordered if g not in lbankgrids and g not in rbankgrids]

        self.uc.log_info(str(ordered))
        cursor = self.con.cursor()
        for qry, vals in sqls:
            try:
                cursor.execute(qry, vals)
            except Exception as e:
                self.uc.log_info(traceback.format_exc())
                continue
        self.con.commit()

        self.schematized_xsections_lyr.triggerRepaint()

    def schematize_leftbanks(self, lbank_feat):
        """
        Schematizing left bank and saving to GeoPackage.
        """
        try:
            fid = lbank_feat.id()
            left_line = lbank_feat.geometry()
            insert_left_sql = """
            INSERT INTO chan 
                (geom, user_lbank_fid, depinitial, froudc, roughadj, isedn) VALUES 
                (AsGPB(ST_GeomFromText('LINESTRING({0})')), ?,?,?,?,?);"""

            left_segment = self.centroids_of_cells_intersecting_polyline(
                left_line.asPolyline()
            )  # Creates list of pairs of coordinates of the cells that
            # intersect this left bank line (this channel segment).
            vertices = ",".join(("{0} {1}".format(*xy) for xy in left_segment))
            self.execute(
                insert_left_sql.format(vertices),
                (
                    fid,
                    0,
                    0,
                    0,
                    0,
                ),
            )  # Initializes this schematized channel segment with a polyline from
            # the vertices calculated from the intersected centroids of cells.
            qry = """UPDATE chan SET depinitial = ?, froudc = ?, roughadj = ?, isedn = ? WHERE user_lbank_fid= fid;"""
            self.execute(qry, (0, 0, 0, 0))  # Is this necessary? Was not initialized to zeros in previous statement?

        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("WARNING 060319.1618: Error while creating schematic Left banks!.")

    def schematize_rightbanks(self, rbank_feat):
        """
        Schematizing right bank and saving to GeoPackage.
        """
        try:
            fid = rbank_feat.attribute("chan_seg_fid")
            right_line = rbank_feat.geometry()
            insert_right_sql = """
            INSERT INTO rbank 
                (geom, chan_seg_fid) VALUES 
                (AsGPB(ST_GeomFromText('LINESTRING({0})')), ?);"""
            right_segment = self.centroids_of_cells_intersecting_polyline(
                right_line.asPolyline()
            )  # Creates list of pairs of coordinates of the cells that
            # intersect this right bank line (this channel segment).
            vertices = ",".join(("{0} {1}".format(*xy) for xy in right_segment))
            self.execute(
                insert_right_sql.format(vertices), (fid,)
            )  # Initializes this schematized right segment with a polyline from
            # the vertices calculated from the intersected centroids of cells.
        except Exception as e:
            self.uc.log_info(traceback.format_exc())
            self.uc.show_warn("WARNING 220718.0741: Error while creating schematic Right banks!.")

    def centroids_of_cells_intersecting_polyline(self, points):
        """
        Using Bresenham's Line Algorithm on list of points.
        """
        feat = QgsFeature()
        geom = QgsGeometry.fromPolylineXY(points)
        feat.setGeometry(geom)
        # One line only
        lines = (feat,)
        segments = tuple(schematize_lines(lines, self.cell_size, self.x_offset, self.y_offset, feats_only=True))
        segment = segments[0]
        return segment

    @staticmethod
    def trim_xs(xs_features, poly_geom):
        """
        Trimming xs features list to poly_geom boundaries.
        """
        for xs in xs_features:
            xs_geom = xs.geometry()
            trimmed = xs_geom.intersection(poly_geom)
            xs.setGeometry(trimmed)

    @staticmethod
    def shift_line_geom(feature, shift_vector):
        """
        Shifting feature geometry according to poly_geom boundaries.
        """
        geom = feature.geometry()
        polyline = geom.asPolyline()
        for pnt in polyline:
            pnt += shift_vector
        feature.setGeometry(QgsGeometry.fromPolylineXY(polyline))

    @staticmethod
    def bank_stations(sorted_xs, bank_geom):
        """
        Finding crossing points between bank lines and cross sections.
        """
        crossing_points = []
        for xs in sorted_xs:  # For each CS line.
            xs_geom = xs.geometry()
            intersects = xs_geom.intersection(bank_geom)
            if intersects.wkbType == QgsWkbTypes.MultiPoint:
                multi_point = intersects.asMultiPoint()
                if len(multi_point) > 0:
                    crossing_points.append(intersects[0])
            else:
                crossing_points.append(intersects.asPoint())

        return crossing_points  # Returns as many points as user cross sections intersecting this channel segment line.

    @staticmethod
    def closest_nodes(segment_points, bank_points):
        """
        Getting closest vertexes (with its indexes) to the bank points.
        """
        nodes = [segment_points.closestVertex(pnt)[:2] for pnt in bank_points]
        return nodes

    def schematize_xs_with_rotation(self, shifted_xs):
        """
        Rotating and schematizing (sorted and shifted) cross sections using Bresenham's Line Algorithm.
        """
        for xs_feat in shifted_xs:
            geom_poly = xs_feat.geometry().asPolyline()
            start, end = geom_poly[0], geom_poly[-1]
            azimuth = start.azimuth(end)
            if azimuth < 0:
                azimuth += 360
            closest_angle = round(azimuth / 45) * 45
            rotation = closest_angle - azimuth
            end_geom = QgsGeometry.fromPointXY(end)
            end_geom.rotate(rotation, start)
            end_point = end_geom.asPoint()
            points = [start, end_point]
            xs_schema = self.centroids_of_cells_intersecting_polyline(points)
            new_geom = QgsGeometry.fromPolylineXY([QgsPointXY(*xs_schema[0]), QgsPointXY(*xs_schema[-1])])
            xs_feat.setGeometry(new_geom)

    def schematize_xs(self, shifted_xs):
        """
        Schematizing (sorted and shifted) cross sections using Bresenham's Line Algorithm.
        """
        for xs_feat in shifted_xs:
            geom_poly = xs_feat.geometry().asPolyline()
            start, end = geom_poly[0], geom_poly[-1]
            end_geom = QgsGeometry.fromPointXY(end)
            end_point = end_geom.asPoint()
            points = [start, end_point]
            xs_schema = self.centroids_of_cells_intersecting_polyline(points)
            new_geom = QgsGeometry.fromPolylineXY([QgsPointXY(*xs_schema[0]), QgsPointXY(*xs_schema[-1])])
            xs_feat.setGeometry(new_geom)

    @staticmethod
    def interpolate_xs(left_segment, xs_features, idx):
        """
        Interpolating cross sections.
        """
        last_idx = idx[-1]
        isegment = iter(left_segment)
        current_vertex = next(isegment)
        previous_vertex = current_vertex

        xs_iter = iter(xs_features)
        current_xs = next(xs_iter)
        next_xs = next(xs_iter)

        idx_iter = iter(idx)
        current_idx = next(idx_iter)
        next_idx = next(idx_iter)

        start_point = None
        end_point = None
        xs_fid = current_xs.id()
        interpolated = 0
        i = 0
        try:
            while True:
                if i == current_idx:
                    xs_geom = current_xs.geometry()
                    start_point, end_point = xs_geom.asPolyline()
                elif i < next_idx:
                    shift = current_vertex - previous_vertex
                    start_point += shift
                    end_point += shift
                    interpolated = 1
                elif i == next_idx:
                    current_xs = next_xs
                    current_idx = next_idx
                    xs_fid = current_xs.id()
                    interpolated = 0
                    if i == last_idx:
                        xs_geom = current_xs.geometry()
                        start_point, end_point = xs_geom.asPolyline()
                    else:
                        next_xs = next(xs_iter)
                        next_idx = next(idx_iter)
                        continue
                elif i > last_idx:
                    shift = current_vertex - previous_vertex
                    start_point += shift
                    end_point += shift
                    interpolated = 1
                # end_point = self.fix_angle(left_segment, start_point, end_point)
                yield [
                    start_point.x(),
                    start_point.y(),
                    end_point.x(),
                    end_point.y(),
                    xs_fid,
                    interpolated,
                ]
                i += 1
                previous_vertex = current_vertex
                current_vertex = next(isegment)
        except StopIteration:
            return

    @staticmethod
    def fix_angle(segment, start_point, end_point):
        if end_point in segment:
            azimuth = start_point.azimuth(end_point)
            if azimuth < 0:
                azimuth += 360
            if int(round(azimuth)) % 90 == 0:
                rotation = 90
            else:
                rotation = 45
            end_geom = QgsGeometry.fromPointXY(end_point)
            end_geom.rotate(rotation, start_point)
            end_point = end_geom.asPoint()
        else:
            pass
        return end_point

    @staticmethod
    def apply_rotation(start_point, end_point, rotation):
        end_geom = QgsGeometry.fromPointXY(end_point)
        end_geom.rotate(rotation, start_point)
        end_point = end_geom.asPoint()
        return end_point

    @staticmethod
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
            geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
            for key, prev_geom in list(previous.items()):
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
            feat.setId(org_fid)
            feat.setGeometry(geom)
            allfeatures[org_fid] = feat
            index.addFeature(feat)
            previous[org_fid] = geom

        # Clipping interpolated cross sections to original one and between each other
        previous.clear()
        second_clip_xs = []
        for xs in first_clip_xs:
            x1, y1, x2, y2, org_fid, interpolated = xs
            if interpolated == 0:
                second_clip_xs.append(xs)
                continue

            geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
            for fid in index.intersects(geom.boundingBox()):
                f = allfeatures[fid]
                fgeom = f.geometry()
                if fgeom.intersects(geom):
                    end = geom.intersection(fgeom).asPoint()
                    x2, y2 = end.x(), end.y()
                    geom = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
            for key, prev_geom in list(previous.items()):
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

    def copy_features_from_user_channel_layer_to_schematized_channel_layer(self):
        """
        Assigning properties from user layers.
        """
        update_chan = """
        UPDATE chan
        SET
            name = (SELECT name FROM user_left_bank WHERE fid = chan.user_lbank_fid),
            depinitial = (CASE WHEN (SELECT depinitial FROM user_left_bank WHERE fid = chan.user_lbank_fid) NOT NULL THEN
                                 (SELECT depinitial FROM user_left_bank WHERE fid = chan.user_lbank_fid) ELSE 0 END),                  
            froudc = (CASE WHEN (SELECT froudc FROM user_left_bank WHERE fid = chan.user_lbank_fid) NOT NULL THEN
                                 (SELECT froudc FROM user_left_bank WHERE fid = chan.user_lbank_fid) ELSE 0 END),                 
            roughadj = (CASE WHEN (SELECT roughadj FROM user_left_bank WHERE fid = chan.user_lbank_fid) NOT NULL THEN
                                 (SELECT roughadj FROM user_left_bank WHERE fid = chan.user_lbank_fid) ELSE 0 END),          
            isedn = (CASE WHEN (SELECT isedn FROM user_left_bank WHERE fid = chan.user_lbank_fid) NOT NULL THEN
                                 (SELECT isedn FROM user_left_bank WHERE fid = chan.user_lbank_fid) ELSE 0 END),
            notes = (SELECT notes FROM user_left_bank WHERE fid = chan.user_lbank_fid),
            rank = (SELECT rank FROM user_left_bank WHERE fid = chan.user_lbank_fid);
        """
        self.execute(update_chan)

    def copy_features_from_user_xsections_layer_to_schematized_xsections_layer(self):
        """
        Assigning properties from user layers.
        """
        update_chan_elems = """
        UPDATE chan_elems
        SET
            fcn = (SELECT fcn FROM user_xsections WHERE fid = chan_elems.user_xs_fid),
            type = (SELECT type FROM user_xsections WHERE fid = chan_elems.user_xs_fid),
            notes = (SELECT notes FROM user_xsections WHERE fid = chan_elems.user_xs_fid);
        """

        get_val = """SELECT round(ST_Length(ST_Intersection(GeomFromGPB(g.geom), GeomFromGPB(l.geom))), 3)
                FROM grid AS g, chan AS l, ce as chan_elems
                WHERE g.fid = ce.fid AND l.user_lbank_fid = ce.seg_fid;"""

        update_xlen = """
        UPDATE chan_elems
        SET
            xlen = CASE
                   WHEN (
                            SELECT round(ST_Length(ST_Intersection(GeomFromGPB(g.geom), GeomFromGPB(l.geom))), 3)
                            FROM grid AS g, chan AS l
                            WHERE g.fid = chan_elems.fid AND l.user_lbank_fid = chan_elems.seg_fid
                        ) < ? THEN ? 
                ELSE (
                        SELECT round(ST_Length(ST_Intersection(GeomFromGPB(g.geom), GeomFromGPB(l.geom))), 3)
                        FROM grid AS g, chan AS l
                        WHERE g.fid = chan_elems.fid AND l.user_lbank_fid = chan_elems.seg_fid
                     )
                END ;
        """

        #         update_xlen = '''
        #         UPDATE chan_elems
        #         SET
        #             xlen = (
        #                 SELECT round(ST_Length(ST_Intersection(GeomFromGPB(g.geom), GeomFromGPB(l.geom))), 3)
        #                 FROM grid AS g, chan AS l
        #                 WHERE g.fid = chan_elems.fid AND l.user_lbank_fid = chan_elems.seg_fid
        #                 );
        #         '''

        #         self.execute(get_val)
        self.execute(update_chan_elems)
        self.execute(update_xlen, (self.cell_size, self.cell_size))

    # def copy_features_from_user_channel_layer_to_schematized_channel_layer(self):
    #     """
    #     Assigning properties from user layers.
    #     """
    #     update_chan = '''
    #     UPDATE chan
    #     SET
    #         name = (SELECT name FROM user_left_bank WHERE fid = chan.user_lbank_fid),
    #         depinitial = (CASE WHEN (SELECT depinitial FROM user_left_bank WHERE fid = chan.user_lbank_fid) NOT NULL THEN
    #                              (SELECT depinitial FROM user_left_bank WHERE fid = chan.user_lbank_fid) ELSE 0 END),
    #         froudc = (CASE WHEN (SELECT froudc FROM user_left_bank WHERE fid = chan.user_lbank_fid) NOT NULL THEN
    #                              (SELECT froudc FROM user_left_bank WHERE fid = chan.user_lbank_fid) ELSE 0 END),
    #         roughadj = (CASE WHEN (SELECT roughadj FROM user_left_bank WHERE fid = chan.user_lbank_fid) NOT NULL THEN
    #                              (SELECT roughadj FROM user_left_bank WHERE fid = chan.user_lbank_fid) ELSE 0 END),
    #         isedn = (CASE WHEN (SELECT isedn FROM user_left_bank WHERE fid = chan.user_lbank_fid) NOT NULL THEN
    #                              (SELECT isedn FROM user_left_bank WHERE fid = chan.user_lbank_fid) ELSE 0 END),
    #         notes = (SELECT notes FROM user_left_bank WHERE fid = chan.user_lbank_fid),
    #         rank = (SELECT rank FROM user_left_bank WHERE fid = chan.user_lbank_fid);
    #     '''
    #     update_chan_elems = '''
    #     UPDATE chan_elems
    #     SET
    #         fcn = (SELECT fcn FROM user_xsections WHERE fid = chan_elems.user_xs_fid),
    #         type = (SELECT type FROM user_xsections WHERE fid = chan_elems.user_xs_fid),
    #         notes = (SELECT notes FROM user_xsections WHERE fid = chan_elems.user_xs_fid);
    #     '''
    #     update_xlen = '''
    #     UPDATE chan_elems
    #     SET
    #         xlen = (
    #             SELECT round(ST_Length(ST_Intersection(GeomFromGPB(g.geom), GeomFromGPB(l.geom))), 3)
    #             FROM grid AS g, chan AS l
    #             WHERE g.fid = chan_elems.fid AND l.user_lbank_fid = chan_elems.seg_fid
    #             );
    #     '''
    #     self.execute(update_chan)
    #     self.execute(update_chan_elems)
    #     self.execute(update_xlen)

    def copy_user_xs_data_to_schem(self):
        qry_copy_r = """UPDATE chan_r SET
        bankell = (SELECT ucx.bankell FROM user_chan_r AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
        bankelr = (SELECT ucx.bankelr FROM user_chan_r AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
        fcw = (SELECT ucx.fcw FROM user_chan_r AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
        fcd = (SELECT ucx.fcd FROM user_chan_r AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid);"""
        self.execute(qry_copy_r)

        qry_copy_t = """UPDATE chan_t SET
        bankell = (SELECT ucx.bankell FROM user_chan_t AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
        bankelr = (SELECT ucx.bankelr FROM user_chan_t AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
        fcw = (SELECT ucx.fcw FROM user_chan_t AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
        fcd = (SELECT ucx.fcd FROM user_chan_t AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
        zl = (SELECT ucx.zl FROM user_chan_t AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
        zr = (SELECT ucx.zr FROM user_chan_t AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid);
        """
        self.execute(qry_copy_t)

        qry_copy_v = """UPDATE chan_v SET
                bankell = (SELECT ucx.bankell FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                bankelr = (SELECT ucx.bankelr FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                fcd = (SELECT ucx.fcd FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                a1 = (SELECT ucx.a1 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                a2 = (SELECT ucx.a2 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                b1 = (SELECT ucx.b1 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                b2 = (SELECT ucx.b2 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                c1 = (SELECT ucx.c1 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                c2 = (SELECT ucx.c2 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                excdep = (SELECT ucx.excdep FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                a11 = (SELECT ucx.a11 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                a22 = (SELECT ucx.a22 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                b11 = (SELECT ucx.b11 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                b22 = (SELECT ucx.b22 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                c11 = (SELECT ucx.c11 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                c22 = (SELECT ucx.c22 FROM user_chan_v AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid);
                """
        self.execute(qry_copy_v)

        qry_copy_n = """UPDATE chan_n SET
                nxsecnum = (SELECT ucx.nxsecnum FROM user_chan_n AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid),
                xsecname = (SELECT ucx.xsecname FROM user_chan_n AS ucx, user_xsections AS ux, chan_elems AS ce WHERE ucx.user_xs_fid = ux.fid AND ce.fid = elem_fid AND ce.user_xs_fid = ucx.user_xs_fid);     """
        self.execute(qry_copy_n)

        self.clear_tables("xsec_n_data")
        qry_copy_n_data = """INSERT INTO xsec_n_data (chan_n_nxsecnum, xi, yi)
            SELECT
                cn.fid,
                xi,
                yi
            FROM
                user_xsec_n_data AS uxd,
                user_chan_n AS ucn,
                chan_n AS cn
            WHERE ucn.user_xs_fid = uxd.chan_n_nxsecnum AND
                ucn.nxsecnum = cn.nxsecnum;"""
        self.execute(qry_copy_n_data)

    def xs_intervals(self, seg_fids):
        intervals = defaultdict(list)
        for fid in seg_fids:
            req = QgsFeatureRequest().setFilterExpression('"seg_fid" = {} AND "interpolated" = 0'.format(fid))
            req.addOrderBy('"nr_in_seg"')
            xsections_feats = self.schematized_xsections_lyr.getFeatures(req)
            xs_iter = iter(xsections_feats)
            up_feat = next(xs_iter)
            lo_feat = next(xs_iter)
            intervals[fid].append(
                (
                    up_feat["nr_in_seg"],
                    lo_feat["nr_in_seg"],
                    up_feat["fid"],
                    lo_feat["fid"],
                )
            )
            try:
                while True:
                    up_feat = lo_feat
                    lo_feat = next(xs_iter)
                    intervals[fid].append(
                        (
                            up_feat["nr_in_seg"],
                            lo_feat["nr_in_seg"],
                            up_feat["fid"],
                            lo_feat["fid"],
                        )
                    )
            except StopIteration:
                pass
        return intervals

    def xs_distances(self, seg_fids):
        xs_distances = defaultdict(list)
        for fid in seg_fids:
            left_req = QgsFeatureRequest().setFilterExpression('"fid" = {}'.format(fid))
            right_req = QgsFeatureRequest().setFilterExpression('"chan_seg_fid" = {}'.format(fid))
            lbank = next(self.schematized_lbank_lyr.getFeatures(left_req))

            try:
                rbank = next(self.schematized_rbank_lyr.getFeatures(right_req))
            except StopIteration:
                rbank = None
            lbank_geom = lbank.geometry()
            if rbank is not None:
                rbank_geom = rbank.geometry()
            req = QgsFeatureRequest().setFilterExpression('"seg_fid" = {}'.format(fid))
            req.addOrderBy('"nr_in_seg"')
            xsections_feats = self.schematized_xsections_lyr.getFeatures(req)
            for xs_feat in xsections_feats:
                xs_geom = xs_feat.geometry()
                xs_geom_line = xs_geom.asPolyline()
                xs_start = QgsGeometry.fromPointXY(xs_geom_line[0])
                xs_end = QgsGeometry.fromPointXY(xs_geom_line[-1])
                ldist = lbank_geom.lineLocatePoint(xs_start.nearestPoint(lbank_geom))
                if rbank is not None and xs_feat.attribute("rbankgrid") > 0:
                    rdist = rbank_geom.lineLocatePoint(xs_end.nearestPoint(rbank_geom))
                else:
                    rdist = -1

                xs_distances[fid].append((xs_feat.id(), xs_feat["fid"], xs_feat["nr_in_seg"], ldist, rdist))
        return xs_distances

    def calculate_distances(self):
        infinity = float("inf")
        seg_fids = [x[0] for x in self.execute("SELECT fid FROM chan ORDER BY fid;")]
        intervals = self.xs_intervals(seg_fids)
        xs_distances = self.xs_distances(seg_fids)
        distances = OrderedDict()
        for fid in seg_fids:
            seg_intervals = intervals[fid]
            seg_xs = xs_distances[fid]
            iseg_intervals = iter(seg_intervals)
            iseg_xs = iter(seg_xs)
            start, end, start_xs_fid, end_xs_fid = next(iseg_intervals)
            inter_ldist, inter_rdist = 0, 0
            xs_id, xs_fid, nr_in_seg, ldistance, rdistance = next(iseg_xs)
            key = (fid, start_xs_fid, end_xs_fid)
            try:
                while True:
                    if nr_in_seg == start:
                        inter_ldist, inter_rdist = ldistance, rdistance
                        distances[key] = {"rows": [], "start_l": 0, "start_r": 0}
                    elif start < nr_in_seg < end:
                        row = (
                            xs_id,
                            xs_fid,
                            fid,
                            start_xs_fid,
                            end_xs_fid,
                            ldistance - inter_ldist,
                            (rdistance - inter_rdist) if rdistance >= 0 else -1,
                        )
                        distances[key]["rows"].append(row)
                    elif nr_in_seg == end:
                        distances[key]["inter_llen"] = ldistance - inter_ldist
                        distances[key]["inter_rlen"] = rdistance - inter_rdist if rdistance >= 0 else -1
                        try:
                            start, end, start_xs_fid, end_xs_fid = next(iseg_intervals)
                        except StopIteration:
                            start = end
                            start_xs_fid = end_xs_fid
                            end = infinity
                            end_xs_fid = infinity

                        key = (fid, start_xs_fid, end_xs_fid)
                        continue
                    xs_id, xs_fid, nr_in_seg, ldistance, rdistance = next(iseg_xs)
            except StopIteration:
                pass

        for key, interval in distances.items():
            rows = interval["rows"]
            if not "inter_rlen" in interval.keys():
                continue
            if interval["inter_rlen"] < 0:
                continue  # means that interval doesn't have defined right bank, so nothing to do...

            changed = False

            i_start = 0
            while i_start < len(rows):
                # search for not defined right bank distance

                row = rows[i_start]

                if row[6] < 0:  # we've got an undefined right bank
                    if i_start == 0:
                        left_start_distance = 0
                        right_start_distance = 0
                    else:
                        start_row = rows[i_start - 1]
                        left_start_distance = start_row[5]
                        right_start_distance = start_row[6]

                    # search for next define right bank
                    i_end = i_start + 1
                    found = False
                    while i_end < len(rows):
                        row = rows[i_end]
                        found = row[6] >= 0
                        if not found:
                            i_end = i_end + 1
                        else:
                            break

                    # Now we've got the two extremity on the non define rigth bank --> interpolate
                    changed = True
                    if i_end == len(rows):
                        left_end_distance = interval["inter_llen"]
                        right_end_distance = interval["inter_rlen"]
                    else:
                        end_row = rows[i_end]
                        left_end_distance = end_row[5]
                        right_end_distance = end_row[6]

                    interpolate_ratio = (right_end_distance - right_start_distance) / (
                        left_end_distance - left_start_distance
                    )
                    for i in range(i_start, i_end):
                        current_row = list(rows[i])
                        left_distance = current_row[5]
                        right_distance = (
                            left_distance - left_start_distance
                        ) * interpolate_ratio + right_start_distance
                        current_row[6] = right_distance
                        rows[i] = tuple(current_row)
                    i_start = i_end
                else:
                    i_start = i_start + 1

            if changed:
                interval["rows"] = rows

        return distances

    def make_distance_table(self):
        self.clear_tables("chan_elems_interp")
        distances = self.calculate_distances()
        infinity = float("inf")
        qry = """
        INSERT INTO chan_elems_interp
        (id, fid, seg_fid, up_fid, lo_fid, up_dist_left, up_dist_right, up_lo_dist_left, up_lo_dist_right)
        VALUES (?,?,?,?,?,?,?,?,?);"""
        cursor = self.con.cursor()
        for k, val in list(distances.items()):
            xs_rows = val["rows"]
            inter_llen = val["inter_llen"] if "inter_llen" in val else 0
            inter_rlen = val["inter_rlen"] if "inter_rlen" in val else 0
            for xs_id, xs_fid, seg_fid, start, end, ldist, rdist in xs_rows:
                end = end if end < infinity else None
                cursor.execute(
                    qry,
                    (
                        xs_id,
                        xs_fid,
                        seg_fid,
                        start,
                        end,
                        ldist,
                        rdist,
                        inter_llen,
                        inter_rlen,
                    ),
                )
        self.con.commit()


class Confluences(GeoPackageUtils):
    """
    Class for finding confluences.
    """

    def __init__(self, con, iface, lyrs):
        super(Confluences, self).__init__(con, iface)
        self.lyrs = lyrs
        self.schematized_lbank_lyr = lyrs.data["chan"]["qlyr"]
        self.schematized_rbank_lyr = lyrs.data["rbank"]["qlyr"]
        self.user_xsections_lyr = lyrs.data["chan_elems"]["qlyr"]

    def calculate_confluences(self):
        # Iterate over every left bank
        vertex_range = []
        qry = "SELECT fid, rank FROM chan ORDER BY rank, fid;"
        self.schematized_lbank_lyr.startEditing()
        for fid, rank in self.execute(qry):
            # Skip searching for confluences for main channel
            if not rank or rank <= 1:
                continue
            # Selecting left bank segment with given 'fid'
            segment_req = QgsFeatureRequest().setFilterExpression('"fid" = {}'.format(fid))
            segment = next(self.schematized_lbank_lyr.getFeatures(segment_req))
            seg_geom = segment.geometry()
            # Selecting and iterating over potential receivers with higher rank
            rank_req = QgsFeatureRequest().setFilterExpression('"rank" = {}'.format(rank - 1))
            receivers = self.schematized_lbank_lyr.getFeatures(rank_req)
            for lfeat in receivers:
                lfeat_id = lfeat.id()
                req = QgsFeatureRequest().setFilterExpression('"chan_seg_fid" = {}'.format(lfeat_id))
                rfeat = next(self.schematized_rbank_lyr.getFeatures(req))
                left_geom = lfeat.geometry()
                right_geom = rfeat.geometry()
                side = None
                if seg_geom.intersects(left_geom):
                    side = "left"
                elif seg_geom.intersects(right_geom):
                    side = "right"
                if side is not None:
                    new_geom, new_len = self.trim_segment(seg_geom, left_geom, right_geom)
                    self.schematized_lbank_lyr.changeGeometry(fid, new_geom)
                    vertex_range.append((fid, lfeat_id, new_len, new_len + 1, side))
                    break
        self.schematized_lbank_lyr.commitChanges()
        self.schematized_lbank_lyr.updateExtents()
        self.schematized_lbank_lyr.triggerRepaint()
        self.set_confluences(vertex_range)
        self.create_schematized_rbank_lines_from_xs_tips()

    @staticmethod
    def trim_segment(seg_geom, left_geom, right_geom):
        seg_len = len(seg_geom.asPolyline()) - 1
        while True:
            seg_geom.deleteVertex(seg_len)
            if seg_geom.intersects(left_geom) or seg_geom.intersects(right_geom):
                seg_len -= 1
                continue
            else:
                break
        return seg_geom, seg_len

    def set_confluences(self, vertex_range):
        self.clear_tables("chan_confluences")
        insert_qry = """INSERT INTO chan_confluences (conf_fid, type, chan_elem_fid, geom) VALUES (?,?,?,?);"""
        qry = """
        SELECT fid, AsGPB(ST_StartPoint(GeomFromGPB(geom)))
        FROM chan_elems
        WHERE seg_fid = ? AND nr_in_seg = ?;
        """
        for i, (tributary_fid, main_fid, tvertex, mvertex, side) in enumerate(vertex_range, 1):
            tributary_gid, tributary_geom = self.execute(qry, (tributary_fid, tvertex)).fetchone()
            main_gid, main_geom = self.execute(qry, (tributary_fid, mvertex)).fetchone()
            self.execute(insert_qry, (i, 0, tributary_gid, tributary_geom))
            self.execute(insert_qry, (i, 1, main_gid, main_geom))
            self.remove_xs_after_vertex(tributary_fid, tvertex)

    def remove_xs_after_vertex(self, seg_fid, vertex_id):
        del_sql = """DELETE FROM chan_elems WHERE seg_fid = ? AND nr_in_seg > ?;"""
        self.execute(del_sql, (seg_fid, vertex_id))


class FloodplainXS(GeoPackageUtils):
    """
    Class for schematizing floodplain cross-sections.
    """

    def __init__(self, con, iface, lyrs):
        super(FloodplainXS, self).__init__(con, iface)
        self.lyrs = lyrs
        self.cell_size = float(self.get_cont_par("CELLSIZE"))
        self.diagonal = sqrt(2) * self.cell_size
        self.user_fpxs_lyr = lyrs.data["user_fpxsec"]["qlyr"]
        self.schema_fpxs_lyr = lyrs.data["fpxsec"]["qlyr"]
        self.cells_fpxs_lyr = lyrs.data["fpxsec_cells"]["qlyr"]

    def interpolate_points(self, line, step):
        length = line.length()
        reps = round(length / step)
        distance = 0
        while reps >= 0:
            pnt = line.interpolate(distance).asPoint()
            gid = self.grid_on_point(pnt.x(), pnt.y())
            geom = self.single_centroid(gid, buffers=True)
            yield (geom, gid)
            distance = min(length, distance + step)
            reps -= 1

    def schematize_floodplain_xs(self):
        self.clear_tables("fpxsec", "fpxsec_cells")
        fpxsec_qry = "INSERT INTO fpxsec (geom, fid, iflo, nnxsec) VALUES (?,?,?,?);"
        fpxsec_cells_qry = "INSERT INTO fpxsec_cells (geom, grid_fid, fpxsec_fid) VALUES (?,?,?);"
        cell_qry = """SELECT ST_AsText(ST_Centroid(GeomFromGPB(geom))) FROM grid WHERE fid = ?;"""
        point_rows = []
        line_rows = []
        for feat in self.user_fpxs_lyr.getFeatures():
            # Schematizing user floodplain cross-section
            feat_fid = feat["fid"]
            geom = feat.geometry()
            geom_poly = geom.asPolyline()
            start, end = geom_poly[0], geom_poly[-1]
            # Getting start grid fid and its centroid
            start_gid = self.grid_on_point(start.x(), start.y())
            start_wkt = self.execute(cell_qry, (start_gid,)).fetchone()[0]
            start_x, start_y = [float(s) for s in start_wkt.strip("POINT()").split()]
            # Finding shift vector between original start point and start grid centroid
            shift = QgsPointXY(start_x, start_y) - start
            # Shifting start and end point of line
            start += shift
            end += shift
            # Calculating and adjusting line angle
            azimuth = start.azimuth(end)
            if azimuth < 0:
                azimuth += 360
            closest_angle = round(azimuth / 45) * 45
            rotation = closest_angle - azimuth
            end_geom = QgsGeometry.fromPointXY(end)
            end_geom.rotate(rotation, start)
            end_point = end_geom.asPoint()
            # Getting shifted and rotated end grid fid and its centroid
            end_gid = self.grid_on_point(end_point.x(), end_point.y())
            # Finding 'fpxsec_cells' for floodplain cross-section
            step = self.cell_size if closest_angle % 90 == 0 else self.diagonal
            end_wkt = self.execute(cell_qry, (end_gid,)).fetchone()[0]
            end_x, end_y = [float(e) for e in end_wkt.strip("POINT()").split()]
            fpxec_line = QgsGeometry.fromPolylineXY([QgsPointXY(start_x, start_y), QgsPointXY(end_x, end_y)])
            sampling_points = tuple(self.interpolate_points(fpxec_line, step))
            # Adding schematized line for 'fpxsec' table
            line_geom = self.build_linestring([start_gid, end_gid])
            line_rows.append((line_geom, feat_fid, feat["iflo"], len(sampling_points)))
            for point_geom, gid in sampling_points:
                point_rows.append((point_geom, gid, feat_fid))
        # Writing schematized floodplain cross-sections and cells to GeoPackage
        self.execute_many(fpxsec_cells_qry, point_rows)
        self.execute_many(fpxsec_qry, line_rows)
        self.schema_fpxs_lyr.triggerRepaint()
        self.cells_fpxs_lyr.triggerRepaint()
