# -*- coding: utf-8 -*-
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import os
import tempfile

import processing
from PyQt5.QtWidgets import QProgressDialog, QApplication
from osgeo import gdal, osr
from qgis._core import QgsWkbTypes, QgsFeatureRequest, QgsCoordinateReferenceSystem, QgsProject, \
    QgsVectorLayer, QgsProcessingFeatureSourceDefinition
from qgis.core import QgsRasterLayer
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
        self.points_index = None
        self.points_feats = None
        self.populate_point_shape_cbo()
        self.grid_lyr = self.lyrs.data["grid"]["qlyr"]

        # connections
        self.lyr_cbo.currentIndexChanged.connect(self.populate_fields_cbo)
        self.browseSrcBtn.clicked.connect(self.browse_src_pointshape)

    def populate_point_shape_cbo(self):
        """
        Get loaded point shapes into combobox.
        """
        try:
            v_lyrs = self.lyrs.list_group_vlayers()
            for l in v_lyrs:
                if l.geometryType() == QgsWkbTypes.PointGeometry:
                    if l.featureCount() != 0:
                        self.lyr_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())
                else:
                    pass

            r_lyrs = self.lyrs.list_group_rlayers()
            for l in r_lyrs:
                self.lyr_cbo.addItem(l.name(), l.dataProvider().dataSourceUri())

            self.populate_fields_cbo(self.lyr_cbo.currentIndex())
        except Exception as e:
            pass

    def populate_fields_cbo(self, idx):
        """
        Populate the field based on the selected point shape
        """
        uri = self.lyr_cbo.itemData(idx)
        lyr_id = self.lyrs.layer_exists_in_group(uri)
        self.current_lyr = self.lyrs.get_layer_tree_item(lyr_id).layer()

        if isinstance(self.current_lyr, QgsVectorLayer):
            self.point_lyr_field_cbo.setHidden(False)
            self.label_3.setHidden(False)
            self.power_sb.setHidden(False)
            self.label_4.setHidden(False)
            self.neighbors_sb.setHidden(False)
            self.label_5.setHidden(False)
            self.point_lyr_field_cbo.setLayer(self.current_lyr)
            self.point_lyr_field_cbo.setCurrentIndex(0)
        elif isinstance(self.current_lyr, QgsRasterLayer):
            self.point_lyr_field_cbo.setHidden(True)
            self.label_3.setHidden(True)
            self.power_sb.setHidden(True)
            self.label_4.setHidden(True)
            self.neighbors_sb.setHidden(True)
            self.label_5.setHidden(True)
            self.point_lyr_field_cbo.setCurrentIndex(-1)

    def browse_src_pointshape(self):
        """
        Users pick a source point shape not loaded into project.
        """
        s = QSettings()
        last_dtm_shape_dir = s.value("FLO-2D/lastGdsDir", "")
        self.src, __ = QFileDialog.getOpenFileName(None, "Choose elevation point shape...",
                                                   directory=last_dtm_shape_dir)
        if not self.src:
            return
        if self.lyr_cbo.findData(self.src) == -1:
            bname = os.path.basename(self.src)
            self.lyr_cbo.addItem(bname, self.src)
            self.lyr_cbo.setCurrentIndex(len(self.lyr_cbo) - 1)

    def create_elev_rc(self):
        """
        Function to create the outrc
        """

        if self.gutils.is_table_empty("grid"):
            self.uc.bar_warn("There is no grid! Please create it before running tool.")
            return

        self.gutils.clear_tables('outrc')

        outrc_rcdata = []

        grid_extent = self.grid_lyr.extent()
        xMaximum = grid_extent.xMaximum()
        yMaximum = grid_extent.yMaximum() - 0.5
        xMinimum = grid_extent.xMinimum() + 0.5
        yMinimum = grid_extent.yMinimum()

        subcells = processing.run("native:creategrid", {'TYPE': 0,
                                                        'EXTENT': f'{xMinimum},{xMaximum},{yMaximum},{yMinimum} [{self.grid_lyr.crs().authid()}]',
                                                        'HSPACING': 1, 'VSPACING': 1, 'HOVERLAY': 0, 'VOVERLAY': 0,
                                                        'CRS': QgsCoordinateReferenceSystem(
                                                            self.grid_lyr.crs().authid()),
                                                        'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        grid_elements = list(self.grid_lyr.getFeatures())

        n_cells = number_of_elements(self.gutils, self.grid_lyr)

        progDialog = QProgressDialog("Creating rating tables...", None, 0, n_cells)
        progDialog.setModal(True)
        progDialog.setValue(0)
        progDialog.forceShow()

        if isinstance(self.current_lyr, QgsVectorLayer):

            # Prepare the DTM points in a way that it can run the IDW
            dtm_points_array = np.empty((0, 3), dtype=float)
            dtm_points = self.current_lyr.getFeatures()
            for dtm_point in dtm_points:
                dtm_point_attribute = dtm_point.attributes()
                dtm_point_geometry = dtm_point.geometry()
                x = dtm_point_geometry.asPoint().x()
                y = dtm_point_geometry.asPoint().y()
                dtm_points_array = np.append(dtm_points_array,
                                             [[x, y, dtm_point_attribute[self.point_lyr_field_cbo.currentIndex()]]],
                                             axis=0)

            if len(dtm_points_array) / len(grid_elements) < self.min_dtm_sb.value():
                self.uc.log_info("Not sufficient DTM points to run this process!")
                self.uc.bar_info("Not sufficient DTM points to run this process!")
                return

            for j, grid in enumerate(grid_elements):
                grid_geometry = grid.geometry()
                grid_fid = grid.attributes()[0]

                elevations = []
                x_coords = []
                y_coords = []

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
                        x_coords.append(x)
                        y_coords.append(y)
                        elevations.append(elevation_interpolated)

                # Convert the lists to numpy arrays
                x = np.array(x_coords)
                y = np.array(y_coords)
                elevation = np.array(elevations)

                # Define the grid size
                x_unique = np.unique(x)
                y_unique = np.unique(y)

                x_res = len(x_unique)
                y_res = len(y_unique)

                # Create an empty array for the raster
                raster_array = np.full((y_res, x_res), np.nan)

                # Fill the array with elevation data
                for i in range(len(elevation)):
                    x_idx = np.where(x_unique == x[i])[0][0]
                    y_idx = np.where(y_unique == y[i])[0][0]
                    raster_array[y_idx, x_idx] = elevation[i]

                # Replace np.nan with some nodata value if needed, e.g., -9999
                nodata_value = -9999
                raster_array = np.nan_to_num(raster_array, nan=nodata_value)

                # Create the raster file in a temporary location
                temp_file = tempfile.NamedTemporaryFile(suffix='.tif', delete=False)
                temp_file_path = temp_file.name
                temp_file.close()  # We only need the name

                driver = gdal.GetDriverByName('GTiff')
                dataset = driver.Create(temp_file_path, x_res, y_res, 1, gdal.GDT_Float32)

                # Define the geotransform and projection
                x_min, x_max = x_unique.min(), x_unique.max()
                y_min, y_max = y_unique.min(), y_unique.max()

                pixel_width = (x_max - x_min) / (x_res - 1)
                pixel_height = (y_max - y_min) / (y_res - 1)
                geotransform = (x_min, pixel_width, 0, y_min, 0, pixel_height)
                dataset.SetGeoTransform(geotransform)

                # Define a spatial reference
                srs = osr.SpatialReference()
                epsg_code = int(QgsProject.instance().crs().authid().split(":")[1])
                srs.ImportFromEPSG(epsg_code)
                dataset.SetProjection(srs.ExportToWkt())

                # Write the data to the raster band
                band = dataset.GetRasterBand(1)
                band.WriteArray(raster_array)
                band.SetNoDataValue(nodata_value)

                # Flush and close the dataset
                dataset.FlushCache()
                dataset = None

                # Load the temporary raster file into QGIS
                raster_layer = QgsRasterLayer(temp_file_path, "Temporary Raster")

                elev_sorted = sorted(elevations)
                max_elev = max(elevations)
                min_elev = min(elevations)
                dh = (max_elev - min_elev) / self.subd_sb.value()

                # Organize the elevation ranges
                elev_ranges = [round(min_elev + dh * i, 3) for i in range(self.subd_sb.value() + 1)]
                volume = []
                for elev_range in elev_ranges:
                    if round(elev_range, 2) == round(min_elev, 2):
                        volume.append(round(0, 3))
                    else:
                        vol = processing.run("native:rastersurfacevolume",
                                             {'INPUT': raster_layer,
                                              'BAND': 1,
                                              'LEVEL': float(elev_range),
                                              'METHOD': 1,
                                              'OUTPUT_HTML_FILE': 'TEMPORARY_OUTPUT'}
                                             )['VOLUME'] * (- 1)

                        volume.append(round(vol, 3))

                # Prepare data for insertion
                data = [(grid_fid, elev, vol) for elev, vol in zip(elev_ranges, volume)]
                outrc_rcdata.extend(data)  # Extend outrc_rcdata with data for current grid

                del raster_layer
                os.remove(temp_file_path)

                progDialog.setValue(j + 1)

        elif isinstance(self.current_lyr, QgsRasterLayer):

            for j, grid in enumerate(grid_elements):

                grid_fid = grid.attributes()[0]
                self.grid_lyr.selectByIds([grid_fid])

                raster_on_grid = processing.run("gdal:cliprasterbymasklayer",
                               {'INPUT': self.current_lyr,
                                'MASK': QgsProcessingFeatureSourceDefinition(
                                        self.grid_lyr.id(),
                                        selectedFeaturesOnly=True, featureLimit=-1,
                                        geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid),
                                'SOURCE_CRS': None,
                                'TARGET_CRS': QgsProject.instance().crs(),
                                'TARGET_EXTENT': None,
                                'NODATA': None,
                                'ALPHA_BAND': False,
                                'CROP_TO_CUTLINE': True,
                                'KEEP_RESOLUTION': False,
                                'SET_RESOLUTION': False,
                                'X_RESOLUTION': None,
                                'Y_RESOLUTION': None,
                                'MULTITHREADING': False,
                                'OPTIONS': '',
                                'DATA_TYPE': 0,
                                'EXTRA': '',
                                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

                raster_on_grid = QgsRasterLayer(raster_on_grid)
                provider = raster_on_grid.dataProvider()
                band = 1  # Assuming band 1 is the elevation
                stats = provider.bandStatistics(band)
                n_elements = stats.elementCount
                if n_elements < self.min_dtm_sb.value():
                    continue
                min_elev = stats.minimumValue
                max_elev = stats.maximumValue
                dh = (max_elev - min_elev) / self.subd_sb.value()

                # Organize the elevation ranges
                elev_ranges = [round(min_elev + dh * i, 3) for i in range(self.subd_sb.value() + 1)]
                volume = []
                for elev_range in elev_ranges:
                    if round(elev_range, 2) == round(min_elev, 2):
                        volume.append(round(0, 3))
                    else:
                        vol = processing.run("native:rastersurfacevolume",
                                             {'INPUT': raster_on_grid,
                                              'BAND': 1,
                                              'LEVEL': elev_range,
                                              'METHOD': 1,
                                              'OUTPUT_HTML_FILE': 'TEMPORARY_OUTPUT'}
                                             )['VOLUME'] * (- 1)

                        volume.append(round(vol, 3))

                # Prepare data for insertion
                data = [(grid_fid, elev, vol) for elev, vol in zip(elev_ranges, volume)]
                outrc_rcdata.extend(data)  # Extend outrc_rcdata with data for current grid

                QApplication.processEvents()
                progDialog.setValue(j + 1)

                self.grid_lyr.removeSelection()

        # Execute the insert operation outside the loop
        if len(outrc_rcdata) > 0:
            self.gutils.execute_many("INSERT INTO outrc (grid_fid, depthrt, volrt) VALUES (?, ?, ?);", outrc_rcdata)
            self.uc.log_info("Surface Water Rating Tables (OUTRC) created!")
            self.uc.bar_info("Surface Water Rating Tables (OUTRC) created!")
