# -*- coding: utf-8 -*-
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
import math
import os
import tempfile

import processing
from qgis.PyQt.QtWidgets import QProgressDialog, QApplication
from osgeo import gdal, osr
from qgis._core import QgsWkbTypes, QgsFeatureRequest, QgsCoordinateReferenceSystem, QgsProject, \
    QgsVectorLayer, QgsProcessingFeatureSourceDefinition, QgsPointXY, QgsGeometry
from qgis.core import QgsRasterLayer, QgsMapLayerType
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog

from ..flo2d_tools.grid_tools import number_of_elements
from ..geopackage_utils import GeoPackageUtils
from ..user_communication import UserCommunication
from .ui_utils import load_ui

import numpy as np

uiDialog, qtBaseClass = load_ui("sampling_rc")


def idw_interpolation(points, query_point, power, num_neighbors):
    """
    Perform IDW interpolation to estimate the z value at the query_point using nearby points.

    Args:
        points (numpy.ndarray): A numpy array of shape (N, 3) where each row represents (x, y, z) of a known point.
        query_point (numpy.ndarray): The query point as a numpy array of shape (2,) representing (x, y) coordinates.
        power (float): The power parameter for the IDW formula (default is 2).
        num_neighbors (int): Number of nearest neighbors to use for interpolation (default is 3).

    Returns:
        float: The estimated z value at the query_point.
    """
    x_query, y_query = query_point
    distances = np.zeros((len(points),))

    # Calculate distances from query_point to all other points
    distances = np.sqrt((points[:, 0] - x_query) ** 2 + (points[:, 1] - y_query) ** 2)

    # Combine distances with points array
    distances_points = np.column_stack((distances, points))

    # Sort points based on distance
    distances_points = distances_points[distances_points[:, 0].argsort()]

    # Take the closest num_neighbors points
    selected_points = distances_points[:num_neighbors]

    # Calculate weighted z value using IDW formula
    weighted_sum = np.sum(selected_points[:, 3] / selected_points[:, 0] ** power)
    sum_weights = np.sum(1 / selected_points[:, 0] ** power)

    # Avoid division by zero
    if sum_weights == 0:
        return None

    # Calculate the interpolated z value
    interpolated_z = weighted_sum / sum_weights

    return interpolated_z


class SamplingRCDialog(qtBaseClass, uiDialog):

    def __init__(self, con, iface, lyrs, cell_size):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.con = con
        self.iface = iface
        self.lyrs = lyrs
        self.grid = None
        self.cell_size = float(cell_size)
        self.setupUi(self)
        self.gutils = GeoPackageUtils(con, iface)
        self.gpkg_path = self.gutils.get_gpkg_path()
        self.uc = UserCommunication(iface, "FLO-2D")

        self.current_lyr = None
        # self.shape_field = None
        # self.points_index = None
        # self.points_feats = None
        self.populate_layers_cbo()
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]

        # connections
        self.shape_lyr_cbo.currentIndexChanged.connect(self.populate_fields_cbo)

    def populate_layers_cbo(self):
        """
        Get loaded layers into the combobox.
        """
        self.raster_lyr_cbo.clear()
        self.shape_lyr_cbo.clear()
        self.shape_field_cbo.clear()

        gpkg_path = self.gutils.get_gpkg_path()
        gpkg_path_adj = gpkg_path.replace("\\", "/")

        for l in QgsProject.instance().mapLayers().values():
            layer_source_adj = l.source().replace("\\", "/")
            if gpkg_path_adj not in layer_source_adj:
                if l.type() == QgsMapLayerType.RasterLayer:
                    self.raster_lyr_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                elif l.type() == QgsMapLayerType.VectorLayer and l.geometryType() == QgsWkbTypes.PointGeometry:
                    self.shape_lyr_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())

        self.populate_fields_cbo(0)

    def populate_fields_cbo(self, idx):
        """
        Populate the field based on the selected point shape
        """
        uri = self.shape_lyr_cbo.itemData(idx)
        if uri is not None:
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            shape_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

            self.shape_field_cbo.setLayer(shape_lyr)
            self.shape_field_cbo.setCurrentIndex(0)

    def create_elev_rc(self):
        """
        Function to add data to the outrc table
        """

        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            self.uc.log_info("There is no grid! Please create it before running tool.")
            return

        self.gutils.clear_tables('outrc')

        if self.raster_rb.isChecked():
            uri = self.raster_lyr_cbo.itemData(self.raster_lyr_cbo.currentIndex())
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        elif self.vector_rb.isChecked():
            uri = self.shape_lyr_cbo.itemData(self.shape_lyr_cbo.currentIndex())
            lyr_id = self.lyrs.layer_exists_in_group(uri)
            field = self.shape_field_cbo.currentField()
            vector_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

            xs = []
            ys = []

            for i, feat in enumerate(vector_lyr.getFeatures()):
                pt = feat.geometry().asPoint()
                xs.append(round(pt.x(), 10))
                ys.append(round(pt.y(), 10))

                if i + 1 >= 200:
                    break

            unique_x = sorted(set(xs))
            unique_y = sorted(set(ys))

            x_pixel_size = min(
                unique_x[i + 1] - unique_x[i]
                for i in range(len(unique_x) - 1)
                if unique_x[i + 1] > unique_x[i]
            )

            y_pixel_size = min(
                unique_y[i + 1] - unique_y[i]
                for i in range(len(unique_y) - 1)
                if unique_y[i + 1] > unique_y[i]
            )

            feats = list(vector_lyr.getFeatures())

            pt1 = feats[0].geometry().asPoint()
            pt2 = feats[1].geometry().asPoint()

            extent = vector_lyr.extent()

            extent.setXMinimum(extent.xMinimum() - x_pixel_size / 2.0)
            extent.setXMaximum(extent.xMaximum() + x_pixel_size / 2.0)
            extent.setYMinimum(extent.yMinimum() - y_pixel_size / 2.0)
            extent.setYMaximum(extent.yMaximum() + y_pixel_size / 2.0)

            output_raster = os.path.join(tempfile.gettempdir(), "shape_raster.tif")

            params = {
                'INPUT': vector_lyr,
                'FIELD': field,
                'BURN': 0,
                'USE_Z': False,
                'UNITS': 1,
                'WIDTH': x_pixel_size,
                'HEIGHT': y_pixel_size,
                'EXTENT': extent,
                'NODATA': -9999,
                'OPTIONS': '',
                'DATA_TYPE': 5,
                'INIT': None,
                'INVERT': False,
                'EXTRA': '',
                'OUTPUT': output_raster
            }

            result = processing.run("gdal:rasterize", params)

            temp_raster_path = result["OUTPUT"]
            self.current_lyr = QgsRasterLayer(temp_raster_path, "Rasterized Layer")
            # if self.current_lyr.isValid():
            #     QgsProject.instance().addMapLayer(self.current_lyr)

        else:
            self.uc.bar_warn("Please select a valid layer type.")
            self.uc.log_info("Please select a valid layer type.")
            return

        if self.incremental_rb.isChecked():
            method = "incremental"
        elif self.direct_rb.isChecked():
            method = "direct"
        else:
            self.uc.bar_warn("Please select a valid method.")
            self.uc.log_info("Please select a valid method.")
            return

        if self.depth_rb.isChecked():
            depth_wse = "depth"
        elif self.wse_rb.isChecked():
            depth_wse = "wse"
        else:
            self.uc.bar_warn("Please select a valid depth/wse option.")
            self.uc.log_info("Please select a valid depth/wse option.")
            return

        x_samples = self.x_samples_sb.value()
        y_samples = self.y_samples_sb.value()
        number_intervals = self.number_intervals_sb.value()

        outrc_rcdata = []

        features = self.grid_lyr.getFeatures()

        for feat in features:
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                self.uc.bar_warn("No features found. Please create it before running tool.")
                self.uc.log_info("No features found. Please create it before running tool.")
                continue

            cell_area = geom.area()

            points = self.generate_subcell_centers(geom, rows=y_samples, cols=x_samples)
            if not points:
                self.uc.bar_warn(f"No valid points generated for feature ID {feat.id()}. Skipping.")
                self.uc.log_info(f"No valid points generated for feature ID {feat.id()}. Skipping.")
                continue

            elevations = self.sample_raster_values(self.current_lyr, points, band=1)
            if not elevations:
                self.uc.bar_warn(f"No valid elevation samples for feature ID {feat.id()}. Skipping.")
                self.uc.log_info(f"No valid elevation samples for feature ID {feat.id()}. Skipping.")
                continue

            table = self.build_stage_volume_table(
                grid_id=feat.id(),
                method=method,
                elevations=elevations,
                cell_area=cell_area,
                depth_wse=depth_wse,
                intervals=number_intervals
            )

            if not table:
                self.uc.bar_error(f"Failed to build stage-volume table for feature ID {feat.id()}. Skipping.")
                self.uc.log_info(f"Failed to build stage-volume table for feature ID {feat.id()}. Skipping.")
                continue

            outrc_rcdata.extend(table)  # Extend outrc_rcdata with data for current grid

        # Execute the insert operation outside the loop
        if len(outrc_rcdata) > 0:
            self.gutils.execute_many("INSERT INTO outrc (grid_fid, depthrt, volrt) VALUES (?, ?, ?);", outrc_rcdata)
            self.uc.log_info("Surface Water Rating Tables (OUTRC) created!")
            self.uc.bar_info("Surface Water Rating Tables (OUTRC) created!")

    def generate_subcell_centers(self, geom, rows=5, cols=5):
        """
        Generate centers of a structured rows x cols subdivision
        inside the grid cell.
        """
        points = []

        bbox = geom.boundingBox()
        xmin = bbox.xMinimum()
        xmax = bbox.xMaximum()
        ymin = bbox.yMinimum()
        ymax = bbox.yMaximum()

        if cols < 2 or rows < 2:
            return points

        dx = (xmax - xmin) / (cols - 1)
        dy = (ymax - ymin) / (rows - 1)

        for row in range(rows):
            y = ymin + row * dy
            for col in range(cols):
                x = xmin + col * dx
                pt = QgsPointXY(x, y)
                pt_geom = QgsGeometry.fromPointXY(pt)

                if geom.intersects(pt_geom):
                    points.append(pt)

        return points

    def sample_raster_values(self, raster_layer, points, band=1):

        values = []
        provider = raster_layer.dataProvider()

        for i, pt in enumerate(points):

            value, ok = provider.sample(pt, band)

            if ok and value is not None:
                try:
                    values.append(float(value))
                except Exception as e:
                    self.uc.bar_error(f"Conversion error!")
                    self.uc.log_info(f"Conversion error: {e}")

        return values

    def build_stage_volume_table(self, grid_id, method, elevations, cell_area, depth_wse, intervals=10):
        """
        Build stage-volume table using either:

        method="incremental"
            GDS cumulative storage accumulation
            (subcell-based volume increments)

        method="direct"
            Depth integration method
            (average depth multiplied by cell area)
        """

        if not elevations:
            return []

        if cell_area <= 0:
            return []

        z_min = min(elevations)
        z_max = max(elevations)

        if z_max <= z_min:
            return [(grid_id, z_min, 0.0)]

        dz = (z_max - z_min) / float(intervals)
        table = []

        if method == "incremental":

            elevations = sorted(float(z) for z in elevations)
            n = len(elevations)

            if n == 0:
                return []

            subcell_area = cell_area / float(n)
            volume = 0.0

            for k in range(intervals + 1):

                stage = z_min + k * dz
                depth = stage - z_min
                submerged_count = 0

                for z in elevations:
                    if z <= stage:
                        submerged_count += 1
                    else:
                        break

                if k > 0:
                    volume += submerged_count * subcell_area * dz

                if depth_wse == "wse":
                    table.append((grid_id, round(stage, 4), round(volume,4)))
                elif depth_wse == "depth":
                    table.append((grid_id, round(depth, 4), round(volume,4)))

        else:

            n = len(elevations)

            for i in range(intervals + 1):

                stage = z_min + i * dz
                total_depth = 0.0

                for z in elevations:
                    water_depth = max(0.0, stage - z)
                    total_depth += water_depth

                avg_depth = total_depth / n
                volume = avg_depth * cell_area
                if depth_wse == "wse":
                    table.append((grid_id, round(stage, 4), round(volume,4)))
                elif depth_wse == "depth":
                    table.append((grid_id, round(avg_depth, 4), round(volume,4)))

        return table

