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
from qgis._core import QgsProject, QgsMessageLog
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

        self.populate_user_lyrs()

        self.delete_btn.clicked.connect(self.delete_user_lyrs)
        self.cancel_btn.clicked.connect(self.close_dlg)

    def populate_user_lyrs(self):
        """
        Function to populate the user layers in the list view
        """
        layers = []
        for l in QgsProject.instance().mapLayers().values():
            source = str(l.source())
            if l.type() == QgsMapLayerType.VectorLayer:
                layername = source.split("=")[-1]
                if layername not in GeoPackageUtils.current_gpkg_tables:
                    layers.append(l)
            if l.type() == QgsMapLayerType.RasterLayer:
                layername = source.split(":")[-1]
                if layername not in GeoPackageUtils.current_gpkg_tables:
                    layers.append(l)

        items = [f'{i.name()}' for i in layers]
        for s in items:
            i = QListWidgetItem(s)
            i.setFlags(i.flags() | Qt.ItemIsUserCheckable)
            i.setCheckState(Qt.Unchecked)
            self.listWidget.addItem(i)

    def delete_user_lyrs(self):
        """
        Function to delete user layers in the list view
        """
        QApplication.setOverrideCursor(Qt.WaitCursor)
        removed_layers = []
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            if item.checkState() == Qt.Checked:
                gpkg_path = self.gutils.get_gpkg_path()
                QgsMessageLog.logMessage(f'{gpkg_path}|layername={item.text()}')
                QgsMessageLog.logMessage(f'drop table {item.text()}')
                processing.run("native:spatialiteexecutesql", {'DATABASE': gpkg_path,
                                                               'SQL': f'drop table {item.text()}'})
                removed_layers.append(item.text())

        for layer_id, layer in QgsProject.instance().mapLayers().items():
            if layer.name() in removed_layers:
                QgsProject.instance().removeMapLayer(layer_id)

        self.iface.mapCanvas().refreshAllLayers()
        self.uc.bar_info("External layer(s) deleted from the GeoPackage.")
        self.listWidget.clear()
        self.populate_user_lyrs()
        QApplication.restoreOverrideCursor()

    def close_dlg(self):
        """
        Function to close the dialog
        """
        self.close()
