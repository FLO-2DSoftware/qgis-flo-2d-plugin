# -*- coding: utf-8 -*-
# FLO-2D Preprocessor tools for QGIS
# Copyright © 2021 Lutra Consulting for FLO-2D
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version
from os import path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QListView, QListWidgetItem, QApplication
from qgis._core import QgsProject, QgsMessageLog, QgsMapLayer, QgsVectorFileWriter, QgsVectorLayer, QgsRasterLayer
from qgis.core import QgsMapLayerType

from flo2d.geopackage_utils import GeoPackageUtils
from flo2d.gui.ui_utils import load_ui
from flo2d.user_communication import UserCommunication

import processing

uiDialog, qtBaseClass = load_ui("gpkg_management")


class GpkgManagementDialog(qtBaseClass, uiDialog):
    def __init__(self, iface, lyrs, gutils):
        qtBaseClass.__init__(self)
        uiDialog.__init__(self)
        self.setupUi(self)
        self.iface = iface
        self.lyrs = lyrs
        self.gutils = gutils
        self.uc = UserCommunication(iface, "FLO-2D")
        self.project = QgsProject.instance()

        self.populate_user_lyrs()

        self.delete_btn.clicked.connect(self.delete_external_lyrs)

        # self.cancel_btn.clicked.connect(self.close_dlg)
        self.buttonBox.accepted.connect(self.save_layers)

        self.user_ext_btn.clicked.connect(self.user_to_ext)


    def populate_user_lyrs(self):
        """
        Function to populate the user layers in the list view
        """
        external_layers = []
        user_layers = []
        gpkg_path = self.gutils.get_gpkg_path()
        gpkg_path_adj = gpkg_path.replace("\\", "/")

        for l in QgsProject.instance().mapLayers().values():
            layer_source_adj = l.source().replace("\\", "/")
            if gpkg_path_adj in layer_source_adj:
                if l.type() == QgsMapLayerType.VectorLayer:
                    layername_parts = l.source().split("=")
                    layername = layername_parts[-1]
                    if layername not in GeoPackageUtils.current_gpkg_tables:
                        external_layers.append(l)
                elif l.type() == QgsMapLayerType.RasterLayer:
                    layername_parts = l.source().split(":")
                    layername = layername_parts[-1]
                    if layername not in GeoPackageUtils.current_gpkg_tables:
                        external_layers.append(l)
            else:
                if l.type() == QgsMapLayerType.VectorLayer:
                    user_layers.append(l)
                elif l.type() == QgsMapLayerType.RasterLayer:
                    user_layers.append(l)

        items = [f'{i.name()}' for i in external_layers]
        for s in items:
            i = QListWidgetItem(s)
            self.external_list.addItem(i)

        items = [f'{i.name()}' for i in user_layers]
        for s in items:
            i = QListWidgetItem(s)
            self.user_list.addItem(i)

    def ext_to_user(self):
        """
        Function to put an external layer into the user layer
        """
        if self.external_list.selectedItems():
            for item in self.external_list.selectedItems():
                i = QListWidgetItem(item.text())
                self.user_list.addItem(i)
                self.external_list.takeItem(self.external_list.row(item))

    def user_to_ext(self):
        """
        Function to put a user layer into the external layer
        """
        if self.user_list.selectedItems():
            for item in self.user_list.selectedItems():
                i = QListWidgetItem(item.text())
                self.external_list.addItem(i)
                self.user_list.takeItem(self.user_list.row(item))

    def close_dlg(self):
        """
        Function to close the dialog
        """
        self.close()

    def save_layers(self):
        """
        Function to save the layers adjustments done to the geopackage
        """
        # try:
        QApplication.setOverrideCursor(Qt.WaitCursor)

        gpkg_path = self.gutils.get_gpkg_path()

        # Save the information of the user layer on the 'external_layers' table
        if self.user_list.count() != 0:
            for x in range(self.user_list.count()):
                layer_name = self.user_list.item(x).text()
                self.gutils.execute(f"INSERT INTO external_layers (name, type) VALUES ('{layer_name}', 'user');")

        if self.external_list.count() != 0:
            not_added = []
            for x in range(self.external_list.count()):
                layer_name = self.external_list.item(x).text()
                qry = f"SELECT type FROM external_layers WHERE name = '{layer_name}';"
                type = self.gutils.execute(qry).fetchone()
                # Add the ones added by the user and don't run this code for already external layers
                if not type or type[0] == 'user':
                    layer = self.project.mapLayersByName(layer_name)
                    if layer:
                        layer = layer[0]
                    else:
                        continue
                    if layer.type() == QgsMapLayer.VectorLayer and layer.isSpatial():
                        # Save to gpkg
                        options = QgsVectorFileWriter.SaveVectorOptions()
                        options.driverName = "GPKG"
                        options.includeZ = True
                        options.overrideGeometryType = layer.wkbType()
                        options.layerName = layer.name()
                        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
                        QgsVectorFileWriter.writeAsVectorFormatV3(
                            layer,
                            gpkg_path,
                            self.project.transformContext(),
                            options)
                        # Add back to the project
                        gpkg_uri = f"{gpkg_path}|layername={layer.name()}"
                        gpkg_layer = QgsVectorLayer(gpkg_uri, layer.name(), "ogr")
                        self.project.addMapLayer(gpkg_layer, False)
                        gpkg_layer.setRenderer(layer.renderer().clone())
                        gpkg_layer.triggerRepaint()
                        root = self.project.layerTreeRoot()
                        group_name = "External Layers"
                        tree_layer = root.findLayer(layer.id())
                        if tree_layer:
                            layer_parent = tree_layer.parent()
                            if layer_parent and layer_parent.name() == "Storm Drain":
                                group_name = layer_parent.name()
                        flo2d_name = f"FLO-2D_{self.gutils.get_metadata_par('PROJ_NAME')}"
                        flo2d_grp = root.findGroup(flo2d_name)
                        if flo2d_grp.findGroup(group_name):
                            group = flo2d_grp.findGroup(group_name)
                        else:
                            group = flo2d_grp.insertGroup(-1, group_name)
                        group.insertLayer(0, gpkg_layer)

                        layer_gpkg = self.project.mapLayersByName(gpkg_layer.name())[0]
                        myLayerNode = root.findLayer(layer_gpkg.id())
                        myLayerNode.setExpanded(False)

                        # Delete layer that is not in the gpkg
                        self.project.removeMapLayer(layer.id())

                    elif layer.type() == QgsMapLayer.RasterLayer:
                        if layer.dataProvider().bandCount() > 1:
                            not_added.append(layer.name())
                            continue
                        # Save to gpkg
                        layer_name = layer.name().replace(" ", "_")
                        params = {'INPUT': f'{layer.dataProvider().dataSourceUri()}',
                                  'TARGET_CRS': None,
                                  'NODATA': None,
                                  'COPY_SUBDATASETS': False,
                                  'OPTIONS': '',
                                  'EXTRA': f'-co APPEND_SUBDATASET=YES -co RASTER_TABLE={layer_name} -ot Float32',
                                  'DATA_TYPE': 0,
                                  'OUTPUT': f'{gpkg_path}'}

                        processing.run("gdal:translate", params)

                        gpkg_uri = f"GPKG:{gpkg_path}:{layer_name}"
                        gpkg_layer = QgsRasterLayer(gpkg_uri, layer_name, "gdal")
                        self.project.addMapLayer(gpkg_layer, False)
                        gpkg_layer.setRenderer(layer.renderer().clone())
                        gpkg_layer.triggerRepaint()
                        root = self.project.layerTreeRoot()
                        flo2d_name = f"FLO-2D_{self.gutils.get_metadata_par('PROJ_NAME')}"
                        group_name = "External Layers"
                        flo2d_grp = root.findGroup(flo2d_name)
                        if flo2d_grp.findGroup(group_name):
                            group = flo2d_grp.findGroup(group_name)
                        else:
                            group = flo2d_grp.insertGroup(-1, group_name)
                        group.insertLayer(0, gpkg_layer)
                        # Delete layer that is not in the gpkg
                        self.project.removeMapLayer(layer.id())

                        layer_gpkg = self.project.mapLayersByName(gpkg_layer.name())[0]
                        myLayerNode = root.findLayer(layer_gpkg.id())
                        myLayerNode.setExpanded(False)
                    else:
                        not_added.append(layer.name())

                self.gutils.execute(f"INSERT INTO external_layers (name, type) VALUES ('{layer_name}', 'external');")
            QApplication.restoreOverrideCursor()

            if len(not_added) > 0:
                layers_not_added = ', '.join(map(str, not_added))
                for layer_name in not_added:
                    external_layers = self.gutils.execute(
                        f"SELECT fid FROM external_layers WHERE name = '{layer_name}';").fetchall()
                    if external_layers:
                        fid = external_layers[0][0]
                        self.gutils.execute(f"DELETE FROM external_layers WHERE fid = '{fid}';")

                self.uc.show_info(f"The following layers were not added to the GeoPackage: \n\n {layers_not_added}")

        self.uc.bar_info(f"Geopackage Management saved!")
        self.uc.log_info(f"Geopackage Management saved!")

        QApplication.restoreOverrideCursor()
        self.close()

        # except Exception as e:
        #     QApplication.restoreOverrideCursor()
        #     self.uc.log_info("Error saving the geopackage.")
        #     self.uc.show_error(
        #         "Error saving the geopackage."
        #         + "\n__________________________________________________",
        #         e,
        #     )

    def delete_external_lyrs(self):
        """
        Function to delete user layers in the list view
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)
        removed_layers = []
        if len(self.external_list.selectedItems()) != 0:
            for item in self.external_list.selectedItems():

                qry = f"SELECT type FROM external_layers WHERE name = '{item.text()}';"
                type = self.gutils.execute(qry).fetchone()

                if not type or type[0] == 'user':
                    self.uc.bar_info("This is a user layer and cannot be deleted!")
                    self.uc.log_info("This is a user layer and cannot be deleted!")
                    QApplication.restoreOverrideCursor()
                    return

                gpkg_path = self.gutils.get_gpkg_path()
                processing.run("native:spatialiteexecutesql", {'DATABASE': gpkg_path,
                                                               'SQL': f'drop table {item.text()}'})
                removed_layers.append(item.text())
                self.gutils.execute(f"DELETE FROM external_layers WHERE name = '{item.text()}'")

            for layer_id, layer in QgsProject.instance().mapLayers().items():
                if layer.name() in removed_layers:
                    QgsProject.instance().removeMapLayer(layer_id)

            self.iface.mapCanvas().refreshAllLayers()
            self.gutils.execute('VACUUM')
            self.uc.bar_info("External layer(s) deleted from the GeoPackage!")
            self.uc.log_info("External layer(s) deleted from the GeoPackage!")
            self.external_list.clear()
            self.user_list.clear()
            self.populate_user_lyrs()

        else:
            self.uc.bar_info("No external layers found in the GeoPackage!")
            self.uc.log_info("No external layers found in the GeoPackage!")

        QApplication.restoreOverrideCursor()


