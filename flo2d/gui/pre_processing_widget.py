# -*- coding: utf-8 -*-


# FLO-2D Preprocessor tools for QGIS

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version

import processing
from PyQt5.QtCore import QVariant, QUrl
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtGui import QDesktopServices

from ..user_communication import UserCommunication
from .ui_utils import load_ui
from qgis._core import QgsProject, QgsVectorLayer, QgsField, QgsRasterLayer, QgsUnitTypes

uiDialog, qtBaseClass = load_ui("pre_processing_widget")


class PreProcessingWidget(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)

        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.lyrs = lyrs
        self.setupUi(self)

        self.uc = UserCommunication(iface, "FLO-2D")

        # connections raster
        self.populate_raster_cbo()
        self.raster_DEM = None
        self.final_DEM = None

        # connections dam area
        self.dam_layer = None
        self.reservoir = None
        self.dam_area_tool_btn.clicked.connect(self.create_dam_area)
        self.save_changes_dam_btn.clicked.connect(self.save_dam_edits)
        self.delete_dam_btn.clicked.connect(self.delete_cur_dam)
        self.pre_processing_help_btn.clicked.connect(self.pre_processing_help)
        self.estimate_btn.clicked.connect(self.estimate_reservoir)

        # connections channel
        self.channel_layer = None
        self.channel_tool_btn.clicked.connect(self.create_channel)
        self.save_changes_channel_btn.clicked.connect(self.save_channel_edits)
        self.delete_channel_btn.clicked.connect(self.delete_cur_channel)

        self.remove_dam_btn.clicked.connect(self.remove_dam)

    def setup_connection(self):
        """
        Initial settings after connection to GeoPackage.
        """
        self.populate_raster_cbo()
        QgsProject.instance().legendLayersAdded.connect(self.populate_raster_cbo)
        QgsProject.instance().layersRemoved.connect(self.populate_raster_cbo)

    def populate_raster_cbo(self):
        """
        Get loaded rasters into combobox.
        """
        self.srcRasterCbo.clear()
        rasters = self.lyrs.list_group_rlayers()
        for r in rasters:
            self.srcRasterCbo.addItem(r.name(), r.dataProvider().dataSourceUri())

    def create_dam_area(self):
        """
        Start editing the dam area shapefile
        """
        self.dam_layer = QgsVectorLayer('Polygon', 'Dam Area', "memory")
        self.dam_layer.setCrs(QgsProject.instance().crs())
        QgsProject.instance().addMapLayers([self.dam_layer])
        self.iface.setActiveLayer(self.dam_layer)
        self.dam_layer.startEditing()
        self.iface.actionAddFeature().trigger()

    def save_dam_edits(self):
        """
        Save the dam area shapefile
        """
        self.dam_layer.commitChanges()
        self.populate_dam_cbo()

    def delete_cur_dam(self):
        """
        Delete the dam area shapefile
        """
        if not self.dam_area_cbo.count():
            return
        q = "Are you sure you want delete the current dam area?"
        if not self.uc.question(q):
            return

        if self.dam_layer is not None:
            try:
                layer_id = self.dam_layer.id()
                if QgsProject.instance().mapLayers().get(layer_id) is not None:
                    QgsProject.instance().removeMapLayer(layer_id)
            except Exception as e:
                self.uc.show_warn(f"Error deleting dam layer: {str(e)}")

        if self.reservoir is not None:
            try:
                layer_id = self.reservoir.id()
                if QgsProject.instance().mapLayers().get(layer_id) is not None:
                    QgsProject.instance().removeMapLayer(layer_id)
            except Exception as e:
                self.uc.show_warn(f"Error deleting reservoir layer: {str(e)}")

        self.dam_area_cbo.clear()
        self.iface.mapCanvas().refreshAllLayers()

        # disable the buttons
        self.channel_tool_btn.setEnabled(False)
        self.save_changes_channel_btn.setEnabled(False)
        self.delete_channel_btn.setEnabled(False)
        self.label_3.setEnabled(False)

    def pre_processing_help(self):
        QDesktopServices.openUrl(QUrl("https://flo-2dsoftware.github.io/FLO-2D-Documentation/Plugin1000/widgets/pre-processing-tools/Pre-Processing%20Tools.html"))        

    def create_channel(self):
        """
        Start editing the channel shapefile
        """

        # Uncheck the dam area and add transparency to the reservoir
        QgsProject.instance().layerTreeRoot().findLayer(self.dam_layer.id()).setItemVisibilityChecked(False)
        self.reservoir.setOpacity(0.5)
        self.reservoir.triggerRepaint()

        self.channel_layer = QgsVectorLayer('Polygon', 'Channel', "memory")
        self.channel_layer.setCrs(QgsProject.instance().crs())
        QgsProject.instance().addMapLayers([self.channel_layer])
        self.iface.setActiveLayer(self.channel_layer)
        self.channel_layer.startEditing()
        self.iface.actionAddFeature().trigger()

    def save_channel_edits(self):
        """
        Save the channel shapefile
        """

        # adjust the elevations
        channel_pv = self.channel_layer.dataProvider()
        channel_pv.addAttributes([QgsField("Elevation", QVariant.Double)])
        self.channel_layer.updateFields()
        self.channel_layer.commitChanges()

        field_index = self.channel_layer.fields().indexFromName("Elevation")

        h_bottom = self.h_bottom_sb.value()

        self.channel_layer.startEditing()

        for feature in self.channel_layer.getFeatures():
            feature[field_index] = h_bottom
            self.channel_layer.updateFeature(feature)

        self.channel_layer.commitChanges()
        self.populate_channel_cbo()

        # Get the transparency back
        self.reservoir.setOpacity(1)

        self.remove_dam_btn.setEnabled(True)
        self.label.setEnabled(True)
        self.srcRasterCbo.setEnabled(True)

    def delete_cur_channel(self):
        """
        Delete the channel shapefile
        """
        if not self.channel_cbo.count():
            return
        q = "Are you sure you want delete the current channel?"
        if not self.uc.question(q):
            return
        QgsProject.instance().removeMapLayers([self.channel_layer.id()])
        self.remove_dam_btn.setEnabled(False)
        self.label.setEnabled(False)
        self.srcRasterCbo.setEnabled(False)
        self.channel_cbo.clear()
        self.iface.mapCanvas().refreshAllLayers()

    def populate_dam_cbo(self):
        """
        Function to populate the dam cbo once the saving is finished
        """
        self.dam_area_cbo.clear()
        self.dam_area_cbo.addItem(self.dam_layer.name(), self.dam_layer.dataProvider().dataSourceUri())

    def populate_channel_cbo(self):
        """
        Function to populate the channel cbo once the saving is finished
        """
        self.channel_cbo.clear()
        self.channel_cbo.addItem(self.channel_layer.name(), self.channel_layer.dataProvider().dataSourceUri())

    def estimate_reservoir(self):
        """
        Function to estimate the reservoir following the negative buffer methodology
        """
        h_top = self.h_top_sb.value()
        h_bottom = self.h_bottom_sb.value()
        m = self.side_slope_sb.value()
        i = self.intervals_sb.value()

        # check the values
        if m <= 0:
            self.uc.show_warn("Please, select a positive side slope and different than 0!")
            return
        if h_top - h_bottom < 0:
            self.uc.show_warn("Dam elevation minus dam invert elevation should be positive and greater than 0!")
            return

        dam_height = h_top - h_bottom
        distance_to_bottom = dam_height / m

        dx = distance_to_bottom / i
        dy = dx * m

        elevations = []
        distances = []

        for j in range(i):
            elevations.append(round(h_bottom + j * dy, 2))
            distances.append(round(dx + dx * j, 2))

        elevations.append(h_top)

        self.create_reservoir(distances, elevations)

        # enable the buttons
        self.channel_tool_btn.setEnabled(True)
        self.save_changes_channel_btn.setEnabled(True)
        self.delete_channel_btn.setEnabled(True)
        self.label_3.setEnabled(True)

    def create_reservoir(self, distances, elevations):
        """
        Function to create the reservoir
        """
        buffered_layers = []

        # perform the buffer
        for distance in distances:
            alg_params = {'INPUT': self.dam_layer,
                          'DISTANCE': -distance,
                          'SEGMENTS': 5,
                          'END_CAP_STYLE': 0,
                          'JOIN_STYLE': 0,
                          'MITER_LIMIT': 2,
                          'DISSOLVE': False,
                          'OUTPUT': 'TEMPORARY_OUTPUT'}
            buffered = processing.run("native:buffer", alg_params)
            buffered_layers.append(buffered['OUTPUT'])

        # perform the union
        reservoir = processing.run("native:multiunion", {'INPUT': self.dam_layer,
                                                         'OVERLAYS': buffered_layers,
                                                         'OVERLAY_FIELDS_PREFIX': '',
                                                         'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        # adjust the elevations
        reservoir_pv = reservoir.dataProvider()
        reservoir_pv.addAttributes([QgsField("Elevation", QVariant.Double)])
        reservoir.updateFields()

        QgsProject.instance().addMapLayers([reservoir])

        reservoir.startEditing()
        field_index = reservoir.fields().indexFromName("Elevation")

        counter = 0
        for feature in reservoir.getFeatures():
            if counter < (len(elevations)):
                feature[field_index] = elevations[counter]
                reservoir.updateFeature(feature)
                counter += 1

        reservoir.commitChanges()
        self.reservoir = reservoir
        self.iface.mapCanvas().refresh()
        QgsProject.instance().addMapLayers([self.reservoir])

    def remove_dam(self):
        """
        Function to remove the dam
        """

        dam_elevation = self.h_top_sb.value()

        file_dialog = QFileDialog()
        file_dialog.setAcceptMode(QFileDialog.AcceptSave)
        file_dialog.setNameFilter("GeoTIFF files (*.tif *.tiff);;All files (*.*)")
        file_dialog.setDefaultSuffix("tif")

        if file_dialog.exec_():
            file_path = file_dialog.selectedFiles()[0]
        else:
            self.uc.show_warn("Save canceled.")
            return

        # smooth the channel
        channel_smooth = processing.run("native:smoothgeometry", {'INPUT': self.channel_layer,
                                                                  'ITERATIONS': 5,
                                                                  'OFFSET': 0.25,
                                                                  'MAX_ANGLE': 180,
                                                                  'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        # difference reservoir - smoothed
        difference = processing.run("native:difference", {'INPUT': self.reservoir,
                                                          'OVERLAY': channel_smooth,
                                                          'OUTPUT': 'TEMPORARY_OUTPUT',
                                                          'GRID_SIZE': None})['OUTPUT']

        # merge difference - smoothed
        merge = processing.run("native:mergevectorlayers", {'LAYERS': [difference, channel_smooth],
                                                            'CRS': None,
                                                            'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        # dissolve
        dissolved = processing.run("native:dissolve", {'INPUT': merge,
                                                       'FIELD': ['Elevation'],
                                                       'SEPARATE_DISJOINT': False,
                                                       'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        self.raster_DEM = QgsRasterLayer(self.srcRasterCbo.itemData(self.srcRasterCbo.currentIndex()))

        # rasterize (need to get the raster pixel size)
        rasterized = processing.run("gdal:rasterize", {'INPUT': dissolved,
                                                       'FIELD': 'Elevation',
                                                       'BURN': 0,
                                                       'USE_Z': False,
                                                       'UNITS': 0,
                                                       'WIDTH': self.raster_DEM.rasterUnitsPerPixelX(),
                                                       'HEIGHT': self.raster_DEM.rasterUnitsPerPixelY(),
                                                       'EXTENT': None,
                                                       'NODATA': 0,
                                                       'OPTIONS': '',
                                                       'DATA_TYPE': 5,
                                                       'INIT': None,
                                                       'INVERT': False,
                                                       'EXTRA': '',
                                                       'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        table = processing.run("native:rastersurfacevolume", {'INPUT': rasterized,
                                                              'BAND': 1,
                                                              'LEVEL': dam_elevation,
                                                              'METHOD': 1,
                                                              'OUTPUT_TABLE': 'TEMPORARY_OUTPUT'})

        if QgsProject.instance().crs().mapUnits() == QgsUnitTypes.DistanceMeters:
            area_unit = "km²"
            volume_unit = "M m³"
            area_conversion = 1000000
            volume_conversion = 1000000
        else:
            area_unit = "acres"
            volume_unit = "acre-foot"
            area_conversion = 4047
            volume_conversion = 43560

        formatted_output = f"{'='*30}\nArea ({area_unit}): {round(table['AREA']/area_conversion, 2)}\nVolume ({volume_unit}): {round(table['VOLUME']/volume_conversion, 2)}\n{'='*30}"
        self.results_te.setText(formatted_output)

        # merge raster
        self.final_DEM = processing.run("gdal:merge", {'INPUT': [self.raster_DEM, rasterized],
                                                       'PCT': False,
                                                       'SEPARATE': False,
                                                       'NODATA_INPUT': None,
                                                       'NODATA_OUTPUT': None,
                                                       'OPTIONS': '',
                                                       'EXTRA': '',
                                                       'DATA_TYPE': 5,
                                                       'OUTPUT': file_path})['OUTPUT']

        QgsProject.instance().addMapLayers([QgsRasterLayer(self.final_DEM, 'Modified DEM')])

        if self.uc.question(f"Would you like to remove the intermediate calculation shapefiles?"):
            QgsProject.instance().removeMapLayers([self.channel_layer.id()])
            QgsProject.instance().removeMapLayers([self.dam_layer.id()])
            QgsProject.instance().removeMapLayers([self.reservoir.id()])
            return
        else:
            return
