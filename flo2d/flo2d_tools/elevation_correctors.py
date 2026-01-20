# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

import functools
import time
from collections import defaultdict

from PyQt5.QtWidgets import QMessageBox
from qgis._core import QgsMessageLog, QgsSpatialIndex
from qgis.analysis import QgsZonalStatistics
from qgis.core import (
    NULL,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsVectorLayer,
    QgsWkbTypes,
)
from PyQt5.QtCore import QMetaType

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version


from .grid_tools import (
    TINInterpolator,
    gridRegionGenerator,
    poly2grid,
    poly2poly,
    polygons_statistics,
    spatial_centroids_index,
    spatial_index,
)
from .schematic_tools import get_intervals, interpolate_along_line, polys2levees


def timer(func):
    """Print the runtime of the decorated function"""

    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        start_time = time.perf_counter()  # 1
        value = func(*args, **kwargs)
        end_time = time.perf_counter()  # 2
        run_time = end_time - start_time  # 3
        print(f"Finished {func.__name__!r} in {run_time:.4f} secs")
        return value

    return wrapper_timer


class ElevationCorrector(object):
    ELEVATION_FIELD = "elev"
    CORRECTION_FIELD = "correction"
    VIRTUAL_SUM = "elev_correction"

    def __init__(self, gutils, lyrs):
        self.gutils = gutils
        self.lyrs = lyrs

        self.user_points = None
        self.user_polygons = None

        self.filter_expression = ""
        self.field_expression = """
        CASE 
        WHEN ("{0}" IS NOT NULL AND "{1}" IS NULL) THEN "{0}" 
        WHEN ("{0}" IS NULL AND "{1}" IS NOT NULL) THEN "{1}" 
        WHEN ("{0}" is NOT NULL AND "{1}" IS NOT NULL) THEN "{0}" + "{1}"
        END
        """

        self.new_filter_expression = ""

    def setup_elevation_layers(self):
        self.user_points = self.lyrs.data["user_elevation_points"]["qlyr"]
        self.user_polygons = self.lyrs.data["user_elevation_polygons"]["qlyr"]

    def set_filter(self):
        self.user_points.setSubsetString(self.new_filter_expression)
        self.user_polygons.setSubsetString(self.new_filter_expression)

    def clear_filter(self):
        self.user_points.setSubsetString("")
        self.user_polygons.setSubsetString("")

    def add_virtual_sum(self, layer):
        expr = self.field_expression.format(self.ELEVATION_FIELD, self.CORRECTION_FIELD)
        field = QgsField(self.VIRTUAL_SUM, QMetaType.Double)
        layer.addExpressionField(expr, field)

    def remove_virtual_sum(self, layer):
        index = layer.fields().lookupField(self.VIRTUAL_SUM)
        layer.removeExpressionField(index)

    @staticmethod
    def duplicate_layer(vlayer, request=None):
        if request is None:
            feats = [feat for feat in vlayer.getFeatures()]
        else:
            feats = [feat for feat in vlayer.getFeatures(request)]
        vtype = vlayer.geometryType()
        if vtype == QgsWkbTypes.PointGeometry:
            uri_type = "Point"
        elif vtype == QgsWkbTypes.LineGeometry:
            uri_type = "LineString"
        elif vtype == QgsWkbTypes.PolygonGeometry:
            uri_type = "Polygon"
        else:
            return
        epsg = vlayer.crs().authid()
        duplicate_name = "{}_duplicated".format(vlayer.name())
        mem_layer = QgsVectorLayer(f"{uri_type}?crs={epsg}", duplicate_name, "memory")
        mem_layer_data = mem_layer.dataProvider()
        attr = vlayer.dataProvider().fields().toList()
        mem_layer_data.addAttributes(attr)
        mem_layer.updateFields()
        mem_layer_data.addFeatures(feats)
        return mem_layer

    @staticmethod
    def buffer_layer(vlayer, buffer_field, request=None):
        epsg = vlayer.crs().authid()
        duplicate_name = "{}_duplicated".format(vlayer.name())
        mem_layer = QgsVectorLayer(f"Polygon?crs={epsg}", duplicate_name, "memory")
        mem_layer_data = mem_layer.dataProvider()
        attr = vlayer.dataProvider().fields().toList()
        mem_layer_data.addAttributes(attr)
        mem_layer.updateFields()
        buffer_feats = []
        for feat in vlayer.getFeatures() if request is None else vlayer.getFeatures(request):
            buffer_feat = QgsFeature(feat)
            buffer_value = feat[buffer_field]
            if not buffer_value:
                continue
            buffer_geom = feat.geometry().buffer(buffer_value, 5)
            buffer_feat.setGeometry(buffer_geom)
            buffer_feats.append(buffer_feat)
        mem_layer_data.addFeatures(buffer_feats)
        return mem_layer

    @staticmethod
    def centroid_layer(vlayer, request=None):
        if request is None:
            feats = [feat for feat in vlayer.getFeatures()]
        else:
            feats = [feat for feat in vlayer.getFeatures(request)]
        for feat in feats:
            feat.setGeometry(feat.geometry().centroid())
        epsg = vlayer.crs().authid()
        centroids_name = "{}_centroids".format(vlayer.name())
        mem_layer = QgsVectorLayer("{}?crs={}".format("Point", epsg), centroids_name, "memory")
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
        self.user_levees = self.lyrs.data["user_levee_lines"]["qlyr"]
        self.schema_levees = self.lyrs.data["levee_data"]["qlyr"]
        self.new_filter_expression = "membership IN ('all', 'levees')"
        self.filter_expression = "SELECT * FROM {} WHERE membership = 'all' OR membership = 'levees';"

    @timer
    def elevation_from_points(self, search_buffer):
        cur = self.gutils.con.cursor()
        for feat in self.user_levees.getFeatures():
            rect_bounds = feat.geometry().buffer(search_buffer, 5).boundingBox()
            user_point_features = self.user_points.getFeatures(QgsFeatureRequest().setFilterRect(rect_bounds))
            try:
                qry = "UPDATE levee_data SET levcrest = ? WHERE fid = ?;"
                intervals = get_intervals(feat, user_point_features, self.ELEVATION_FIELD, search_buffer)
            except TypeError:
                qry = "UPDATE levee_data SET levcrest = levcrest + ? WHERE fid = ?;"
                intervals = get_intervals(feat, user_point_features, self.CORRECTION_FIELD, search_buffer)
            interpolated = interpolate_along_line(feat, self.schema_levees.getFeatures(), intervals)
            try:
                for elev, fid in interpolated:
                    cur.execute(qry, (round(elev, 4), fid))
            except IndexError:
                continue
        self.gutils.con.commit()

    def elevation_from_lines(self):
        """
        This function corrects the levcrest on levees with improved performance.
        """

        user_levee_lines = self.lyrs.data["user_levee_lines"]["qlyr"]

        # Collect features into a batch
        user_levee_features = [
            (feature["fid"], feature["elev"], feature["correction"])
            for feature in user_levee_lines.getFeatures()
        ]

        # Separate cases based on conditions
        updates = {"elev_and_cor": [], "elev_only": [], "cor_only": []}

        for fid, elev, cor in user_levee_features:
            if elev == NULL and cor == NULL:
                continue
            elif elev != NULL and cor != NULL:
                updates["elev_and_cor"].append((fid, elev, cor))
            elif elev != NULL and cor == NULL:
                updates["elev_only"].append((fid, elev))
            elif elev == NULL and cor != NULL:
                updates["cor_only"].append((fid, cor))

        # Perform batch updates
        if updates["elev_and_cor"]:
            fids = ", ".join(str(fid) for fid, _, _ in updates["elev_and_cor"])
            self.gutils.execute(f"""
                UPDATE levee_data AS ld
                SET levcrest = (
                    SELECT ull.correction + ull.elev
                    FROM user_levee_lines AS ull
                    WHERE ull.fid = ld.user_line_fid
                    LIMIT 1 
                )
                WHERE ld.user_line_fid IN ({fids});
            """)

        if updates["elev_only"]:
            fids = ", ".join(str(fid) for fid, _ in updates["elev_only"])
            self.gutils.execute(f"""
                UPDATE levee_data AS ld
                SET levcrest = (
                    SELECT ull.elev
                    FROM user_levee_lines AS ull
                    WHERE ull.fid = ld.user_line_fid
                    LIMIT 1 
                )
                WHERE ld.user_line_fid IN ({fids});
            """)

        if updates["cor_only"]:
            fids = ", ".join(str(fid) for fid, _ in updates["cor_only"])
            self.gutils.execute(f"""
                UPDATE levee_data AS ld
                SET levcrest = levcrest + (
                    SELECT ull.correction
                    FROM user_levee_lines AS ull
                    WHERE ull.fid = ld.user_line_fid
                    LIMIT 1 
                )
                WHERE ld.user_line_fid IN ({fids});
            """)


    @timer
    def elevation_from_polygons(self):
        qry_values = []
        qry = "UPDATE levee_data SET levcrest = ? WHERE fid = ?;"
        for feat in self.user_levees.getFeatures():
            poly_values = polys2levees(
                feat,
                self.user_polygons,
                self.schema_levees,
                self.ELEVATION_FIELD,
                self.CORRECTION_FIELD,
            )
            for elev, fid in poly_values:
                qry_values.append((round(elev, 4), fid))
        cur = self.gutils.con.cursor()
        cur.executemany(qry, qry_values)
        self.gutils.con.commit()


class GridElevation(ElevationCorrector):
    def __init__(self, gutils, lyrs):
        super(GridElevation, self).__init__(gutils, lyrs)

        self.grid = None
        self.blocked_areas = None

        self.threshold = 1
        self.only_selected = None
        self.request = None

    def setup_layers(self):
        self.setup_elevation_layers()
        self.request = QgsFeatureRequest().setFilterFids(self.user_polygons.selectedFeatureIds())
        self.grid = self.lyrs.data["grid"]["qlyr"]
        self.blocked_areas = self.lyrs.data["user_blocked_areas"]["qlyr"]
        self.new_filter_expression = "membership IN ('all', 'grid')"
        self.filter_expression = "SELECT * FROM {} WHERE membership = 'all' OR membership = 'grid';"

    def elevation_from_polygons(self):

        if self.user_polygons.featureCount() <= 0:
            ms_box = QMessageBox(
                QMessageBox.Critical,
                "Error",
                "Please, define Elevation Polygon."
            )
            ms_box.exec_()
            ms_box.show()
            return

        if self.only_selected is True:
            request = self.request
        else:
            request = None
        set_qry = "UPDATE grid SET elevation = ? WHERE fid = ?;"
        add_qry = "UPDATE grid SET elevation = elevation + ? WHERE fid = ?;"
        set_add_qry = "UPDATE grid SET elevation = ? + ? WHERE fid = ?;"
        cur = self.gutils.con.cursor()
        cellSize = float(self.gutils.get_cont_par("CELLSIZE"))
        for el, cor, fid in poly2grid(
            cellSize,
            self.grid,
            self.user_polygons,
            request,
            True,
            False,
            False,
            self.threshold,
            self.ELEVATION_FIELD,
            self.CORRECTION_FIELD,
        ):
            el_null = el == NULL
            cor_null = cor == NULL
            if not el_null:
                el = round(el, 4)
            if not cor_null:
                cor = round(cor, 4)

            if not el_null and cor_null:
                cur.execute(set_qry, (el, fid))
            elif el_null and not cor_null:
                cur.execute(add_qry, (cor, fid))
            elif not el_null and not cor_null:
                cur.execute(set_add_qry, (el, cor, fid))

        self.gutils.con.commit()

    def elevation_from_tin(self):

        if self.user_polygons.featureCount() <= 0 or self.user_points.featureCount() <= 0:
            ms_box = QMessageBox(
                QMessageBox.Critical,
                "Error",
                "Please, define Elevation Polygon & Elevation points."
            )
            ms_box.exec_()
            ms_box.show()
            return

        if self.only_selected is True:
            request = self.request
        else:
            request = None
        self.add_virtual_sum(self.user_points)
        tin = TINInterpolator(self.user_points, self.VIRTUAL_SUM)
        tin.setup_layer_data()
        cellSize = float(self.gutils.get_cont_par("CELLSIZE"))

        grid_fids = [
            val[-1]
            for val in poly2grid(
                cellSize,
                self.grid,
                self.user_polygons,
                request,
                True,
                True,
                False,
                self.threshold,
            )
        ]

        request = QgsFeatureRequest().setFilterFids(grid_fids)
        qry_values = []
        qry = "UPDATE grid SET elevation = ? WHERE fid = ?;"
        for feat in self.grid.getFeatures(request):
            geom = feat.geometry()
            centroid = geom.centroid().asPoint()
            succes, value = tin.tin_at_xy(centroid.x(), centroid.y())
            if succes != 0:
                continue
            qry_values.append((round(value, 4), feat.id()))
        cur = self.gutils.con.cursor()
        cur.executemany(qry, qry_values)
        self.gutils.con.commit()
        self.remove_virtual_sum(self.user_points)

    def tin_elevation_within_polygons(self):

        if self.user_polygons.featureCount() <= 0:
            ms_box = QMessageBox(
                QMessageBox.Critical,
                "Error",
                "Please, define Elevation Polygon."
            )
            ms_box.exec_()
            ms_box.show()
            return

        if self.only_selected is True:
            request = self.request
        else:
            request = None
        poly_feats = (
            self.user_polygons.getFeatures() if self.only_selected is False else self.user_polygons.getFeatures(request)
        )
        user_lines = [feat.geometry().convertToType(QgsWkbTypes.LineGeometry) for feat in poly_feats]
        allfeatures, index = spatial_index(self.grid)
        boundary_grid_fids = []
        for line_geom in user_lines:
            line_geom_geos = line_geom.constGet()
            line_geom_engine = QgsGeometry.createGeometryEngine(line_geom_geos)
            line_geom_engine.prepareGeometry()
            for gid in index.intersects(line_geom.boundingBox()):
                grid_feat = allfeatures[gid]
                grid_geom = grid_feat.geometry()
                if line_geom_engine.intersects(grid_geom.constGet()):
                    boundary_grid_fids.append(gid)
        boundary_request = QgsFeatureRequest().setFilterFids(boundary_grid_fids)
        grid_centroids = self.centroid_layer(self.grid, boundary_request)
        tin = TINInterpolator(grid_centroids, "elevation")
        cellSize = float(self.gutils.get_cont_par("CELLSIZE"))
        tin.setup_layer_data()
        grid_fids = [
            val[-1]
            for val in poly2grid(
                cellSize,
                self.grid,
                self.user_polygons,
                request,
                True,
                True,
                False,
                self.threshold,
            )
        ]
        request = QgsFeatureRequest().setFilterFids(grid_fids)
        qry_values = []
        qry = "UPDATE grid SET elevation = ? WHERE fid = ?;"
        for feat in self.grid.getFeatures(request):
            QgsMessageLog.logMessage(str(feat.id()))
            geom = feat.geometry()
            centroid = geom.centroid().asPoint()
            succes, value = tin.tin_at_xy(centroid.x(), centroid.y())
            if succes != 0:
                continue
            qry_values.append((round(value, 4), feat.id()))
        cur = self.gutils.con.cursor()
        cur.executemany(qry, qry_values)
        self.gutils.con.commit()

    def elevation_within_arf(self, calculation_type):

        if self.blocked_areas.featureCount() <= 0:
            ms_box = QMessageBox(
                QMessageBox.Critical,
                "Error",
                "Please, define Blocked Areas."
            )
            ms_box.exec_()
            ms_box.show()
            return

        if calculation_type == "Mean":

            def calculation_method(vals):
                return sum(vals) / len(vals)

        elif calculation_type == "Max":

            def calculation_method(vals):
                return max(vals)

        elif calculation_type == "Min":

            def calculation_method(vals):
                return min(vals)

        else:
            raise ValueError
        feats = self.grid.getFeatures()
        feat = next(feats)
        cell_size = feat.geometry().area()
        qry_values = []
        qry = "UPDATE grid SET elevation = ? WHERE fid = ?;"
        # request = QgsFeatureRequest().setFilterExpression('"calc_arf" = 1')
        request = None
        for fid, parts in poly2poly(self.blocked_areas, self.grid, request, False, "fid", "elevation"):
            gids, elevs, subareas = [], [], []
            for gid, elev, area in parts:
                if area / cell_size < 0.9:
                    continue
                gids.append(gid)
                elevs.append(elev)
            if not elevs:
                continue
            elevation = round(calculation_method(elevs), 4)
            for g in gids:
                qry_values.append((elevation, g))
        cur = self.gutils.con.cursor()
        cur.executemany(qry, qry_values)
        self.gutils.con.commit()


class ExternalElevation(ElevationCorrector):
    def __init__(self, gutils, lyrs):
        super(ExternalElevation, self).__init__(gutils, lyrs)

        self.grid = None
        self.only_centroids = None
        self.threshold = 0.90

        self.polygons = None
        self.elevation_field = None
        self.correction_field = None

        self.statistics = None
        self.raster = None
        self.statistics_per_grid = None

        self.only_selected = None
        self.copy_features = None
        self.request = None

    def setup_internal(self):
        self.setup_elevation_layers()
        self.grid = self.lyrs.data["grid"]["qlyr"]

    def setup_external(self, polygon_lyr, predicate, only_selected=False, copy_features=False):
        self.polygons = polygon_lyr
        self.only_centroids = True if predicate == "centroids within polygons" else False
        self.only_selected = only_selected
        if self.only_selected is True:
            self.request = QgsFeatureRequest().setFilterFids(self.polygons.selectedFeatureIds())
        self.copy_features = copy_features

    def setup_attributes(self, elevation, correction):
        self.elevation_field = elevation
        self.correction_field = correction

    def setup_statistics(self, statistics, raster=None, statistics_per_grid=False):
        self.statistics = statistics
        self.raster = raster
        self.statistics_per_grid = statistics_per_grid

    def import_features(self, fids_values):
        copy_request = QgsFeatureRequest().setFilterFids(list(fids_values.keys()))
        fields = self.user_polygons.fields()
        self.user_polygons.startEditing()
        for feat in self.polygons.getFeatures(copy_request):
            values = fids_values[feat.id()]
            new_feat = QgsFeature()
            new_feat.setFields(fields)
            poly_geom = feat.geometry().asPolygon()
            new_geom = QgsGeometry.fromPolygonXY(poly_geom)
            new_feat.setGeometry(new_geom)
            for key, val in list(values.items()):
                new_feat.setAttribute(key, val)
            new_feat.setAttribute("membership", "grid")
            self.user_polygons.addFeature(new_feat)
        self.user_polygons.commitChanges()
        self.user_polygons.updateExtents()
        self.user_polygons.triggerRepaint()
        self.user_polygons.removeSelection()

    def elevation_attributes(self):
        set_qry = "UPDATE grid SET elevation = ? WHERE fid = ?;"
        add_qry = "UPDATE grid SET elevation = elevation + ? WHERE fid = ?;"
        set_add_qry = "UPDATE grid SET elevation = ? + ? WHERE fid = ?;"
        cellSize = float(self.gutils.get_cont_par("CELLSIZE"))
        poly_list = poly2grid(
            cellSize,
            self.grid,
            self.polygons,
            self.request,
            self.only_centroids,
            True,
            False,
            self.threshold,
            self.elevation_field,
            self.correction_field,
        )
        fids = {}
        qry_values = []
        for fid, el, cor, gid in poly_list:
            el_null = el == NULL
            cor_null = cor == NULL
            if not el_null:
                el = round(el, 4)
            if not cor_null:
                cor = round(cor, 4)

            if not el_null and cor_null:
                qry_values.append((set_qry, (el, gid)))
            elif el_null and not cor_null:
                qry_values.append((add_qry, (cor, gid)))
            elif not el_null and not cor_null:
                qry_values.append((set_add_qry, (el, cor, gid)))

            fids[fid] = {"elev": el, "correction": cor}

        cur = self.gutils.con.cursor()
        for qry, vals in qry_values:
            cur.execute(qry, vals)
        self.gutils.con.commit()
        if self.copy_features is True:
            self.import_features(fids)

    def elevation_grid_statistics(self):
        if self.statistics == "Mean":

            def calculation_method(vals):
                return sum(vals) / len(vals)

        elif self.statistics == "Max":

            def calculation_method(vals):
                return max(vals)

        elif self.statistics == "Min":

            def calculation_method(vals):
                return min(vals)

        else:
            raise ValueError
        cur = self.gutils.con.cursor()
        qry = "UPDATE grid SET elevation = ? WHERE fid = ?;"
        cellSize = float(self.gutils.get_cont_par("CELLSIZE"))
        grid_gen = poly2grid(
            cellSize,
            self.grid,
            self.polygons,
            self.request,
            self.only_centroids,
            True,
            False,
            self.threshold,
        )
        fids_grids = defaultdict(list)
        fids_elevs = {}
        for fid, gid in grid_gen:
            fids_grids[fid].append(gid)
        for fid, grids_fids in list(fids_grids.items()):
            grid_request = QgsFeatureRequest().setFilterFids(grids_fids)
            elevs = []
            for grid_feat in self.grid.getFeatures(grid_request):
                elevs.append(grid_feat["elevation"])
            elevation = round(calculation_method(elevs), 4)
            fids_elevs[fid] = {"elev": elevation}
            for g in grids_fids:
                cur.execute(qry, (elevation, g))
        self.gutils.con.commit()
        if self.copy_features is True:
            self.import_features(fids_elevs)

    def elevation_raster_statistics(self):
        if self.statistics == "Mean":
            stats = QgsZonalStatistics.Mean
        elif self.statistics == "Max":
            stats = QgsZonalStatistics.Max
        elif self.statistics == "Min":
            stats = QgsZonalStatistics.Min
        else:
            raise ValueError
        if self.statistics_per_grid:
            selected_polygons_layer = self.duplicate_layer(self.polygons, self.request)
            grid_fids = set()
            allfeatures, index = spatial_centroids_index(self.grid) if self.only_centroids else spatial_index(self.grid)
            for poly_feat in selected_polygons_layer.getFeatures():
                poly_geom = poly_feat.geometry()
                for gid in index.intersects(poly_geom.boundingBox()):
                    grid_feat = allfeatures[gid]
                    if grid_feat.geometry().intersects(poly_geom):
                        grid_fids.add(gid)
            subgrid_request = QgsFeatureRequest().setFilterFids(list(grid_fids))
            self.polygons = self.duplicate_layer(self.grid, subgrid_request)
            self.only_centroids = True
        else:
            self.polygons = self.duplicate_layer(self.polygons, self.request)
        polygons_statistics(self.polygons, self.raster, stats)
        self.request = None
        self.elevation_field = self.statistics.lower()
        self.correction_field = None
        self.elevation_attributes()
