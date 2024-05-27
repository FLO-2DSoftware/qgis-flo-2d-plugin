# -*- coding: utf-8 -*-

# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import tempfile
from subprocess import PIPE, STDOUT, Popen

import processing
from PyQt5.QtWidgets import QProgressDialog, QApplication
from qgis._core import QgsWkbTypes, QgsGeometry, QgsFeatureRequest, QgsCoordinateReferenceSystem, QgsProject
from qgis.core import QgsRasterLayer
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QFileDialog

from ..flo2d_tools.grid_tools import grid_has_empty_elev, raster2grid, spatial_index, number_of_elements
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
        self.points_index = None
        self.points_feats = None
        self.populate_point_shape_cbo()
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]

        # connections
        self.point_lyr_cbo.currentIndexChanged.connect(self.populate_fields_cbo)
        self.browseSrcBtn.clicked.connect(self.browse_src_pointshape)

    def populate_point_shape_cbo(self):
        """
        Get loaded point shapes into combobox.
        """
        try:
            lyrs = self.lyrs.list_group_vlayers()
            for l in lyrs:
                if l.geometryType() == QgsWkbTypes.PointGeometry:
                    if l.featureCount() != 0:
                        self.point_lyr_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass
            self.populate_fields_cbo(self.point_lyr_cbo.currentIndex())
        except Exception as e:
            pass

    def populate_fields_cbo(self, idx):
        """
        Populate the field based on the selected point shape
        """
        uri = self.point_lyr_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()
        self.point_lyr_field_cbo.setLayer(self.current_lyr)
        self.point_lyr_field_cbo.setCurrentIndex(0)

    def browse_src_pointshape(self):
        """
        Users pick a source point shape not loaded into project.
        """
        s = QSettings()
        last_dtm_shape_dir = s.value("FLO-2D/lastGdsDir", "")
        self.src, __ = QFileDialog.getOpenFileName(None, "Choose elevation point shape...", directory=last_dtm_shape_dir)
        if not self.src:
            return
        if self.point_lyr_cbo.findData(self.src) == -1:
            bname = os.path.basename(self.src)
            self.point_lyr_cbo.addItem(bname, self.src)
            self.point_lyr_cbo.setCurrentIndex(len(self.point_lyr_cbo) - 1)

    def create_elev_rc(self, cell_size):
        """
        Function to create the outrc
        """
        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        self.gutils.clear_tables('outrc')

        grid_extent = self.grid_lyr.extent()
        xMaximum = grid_extent.xMaximum()
        yMaximum = grid_extent.yMaximum() - 0.5
        xMinimum = grid_extent.xMinimum() + 0.5
        yMinimum = grid_extent.yMinimum()

        subcells = processing.run("native:creategrid", {'TYPE': 0,
                                             'EXTENT': f'{xMinimum},{xMaximum},{yMaximum},{yMinimum} [{self.grid_lyr.crs().authid()}]',
                                             'HSPACING': 1, 'VSPACING': 1, 'HOVERLAY': 0, 'VOVERLAY': 0,
                                             'CRS': QgsCoordinateReferenceSystem(self.grid_lyr.crs().authid()),
                                             'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        dtm_points_array = np.empty((0, 3), dtype=float)
        dtm_points = self.current_lyr.getFeatures()
        for dtm_point in dtm_points:
            dtm_point_attribute = dtm_point.attributes()
            dtm_point_geometry = dtm_point.geometry()
            x = dtm_point_geometry.asPoint().x()
            y = dtm_point_geometry.asPoint().y()
            dtm_points_array = np.append(dtm_points_array, [[x, y, dtm_point_attribute[1]]], axis=0)

        grid_elements = self.grid_lyr.getFeatures()

        n_cells = number_of_elements(self.gutils, self.grid_lyr)

        progDialog = QProgressDialog("Creating rating tables...", None, 0, n_cells)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.show()

        outrc_rcdata = []  # Initialize outside the loop to accumulate data

        for j, grid in enumerate(grid_elements):
            grid_geometry = grid.geometry()
            grid_fid = grid.attributes()[0]

            elevations = []
            subcell_centroids = subcells.getFeatures()
            for subcell in subcell_centroids:
                if subcell.geometry().intersects(grid_geometry):
                    subcell_geometry = subcell.geometry()
                    x = subcell_geometry.asPoint().x()
                    y = subcell_geometry.asPoint().y()
                    elevation_interpolated = idw_interpolation(dtm_points_array,
                                                               np.array([x, y]),
                                                               self.power_sb.value(),
                                                               self.neighbors_sb.value())
                    elevations.append(elevation_interpolated)

            elev_sorted = sorted(elevations)
            max_elev = max(elevations)
            min_elev = min(elevations)
            dh = (max_elev - min_elev) / self.subd_sb.value()  # dh subdivided into 11 steps

            # Organize the elevation ranges
            elev_ranges = [round(min_elev + dh * i, 3) for i in range(self.subd_sb.value() + 1)]

            # Calculate the volumes
            volume = []
            for elev_range in elev_ranges:
                if round(elev_range, 2) == round(min_elev, 2):
                    volume.append(round(0, 3))
                    continue
                volume_accumulator = 0
                for elev in elev_sorted:
                    if elev < elev_range:
                        volume_accumulator += (elev_range - elev)
                volume.append(round(volume_accumulator, 3))


            # Prepare data for insertion
            data = [(grid_fid, elev, vol) for elev, vol in zip(elev_ranges, volume)]
            outrc_rcdata.extend(data)  # Extend outrc_rcdata with data for current grid

            QApplication.processEvents()
            progDialog.setValue(j + 1)

        # Execute the insert operation outside the loop
        if outrc_rcdata:
            self.gutils.execute_many("INSERT INTO outrc (grid_fid, depthrt, volrt) VALUES (?, ?, ?);", outrc_rcdata)

        # progDialog = QProgressDialog("Creating rating tables...", None, 0, n_cells)
        # progDialog.setModal(True)
        # progDialog.setValue(0)
        # progDialog.show()
        # j = 0
        #
        # for grid in grid_elements:
        #     outrc_rcdata = []
        #
        #     grid_geometry = grid.geometry()
        #     grid_fid = grid.attributes()[0]
        #
        #     elevations = []
        #     subcell_centroids = subcells.getFeatures()
        #     for subcell in subcell_centroids:
        #         if subcell.geometry().intersects(grid_geometry):
        #             subcell_geometry = subcell.geometry()
        #             x = subcell_geometry.asPoint().x()
        #             y = subcell_geometry.asPoint().y()
        #             elevation_interpolated = idw_interpolation(dtm_points_array, np.array([x, y]))
        #             elevations.append(elevation_interpolated)
        #
        #     elev_sorted = sorted(elevations)
        #     max_elev = max(elevations)
        #     min_elev = min(elevations)
        #     dh = (max_elev - min_elev) / 10  # dh subdivided into 11 steps
        #
        #     # Organize the elevation
        #     elev_ranges = [round(min_elev, 2)]
        #     for i in range(1, 11):
        #         elev_ranges.append(round(min_elev + dh * i, 3))
        #
        #     # Calculate the volumes
        #     volume = []
        #     for elev_range in elev_ranges:
        #         volume_accumulator = 0
        #         for elev in elev_sorted:
        #             if elev < elev_range:
        #                 volume_accumulator += (max_elev - elev)
        #         volume.append(round(volume_accumulator, 3))
        #
        #     data = [(grid_fid, x, y) for x, y in zip(elev_ranges, volume)]
        #     outrc_rcdata.append(data)
        #
        #     self.gutils.execute_many(f"INSERT INTO outrc (grid_fid, depthrt, volrt) VALUES (?, ?, ?);", outrc_rcdata)
        #
        #     j += 1
        #     QApplication.processEvents()
        #     progDialog.setValue(j)
